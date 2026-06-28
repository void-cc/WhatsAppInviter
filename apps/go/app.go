package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"github.com/skip2/go-qrcode"
	"github.com/wailsapp/wails/v2/pkg/runtime"

	"github.com/void-cc/WhatsAppInviter/apps/go/internal/excel"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/message"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/report"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/settings"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/wa"
)

// App is the Wails-bound application backend.
type App struct {
	ctx context.Context

	mu          sync.Mutex
	settings    settings.Settings
	excelPath   string
	table       *excel.SheetTable
	contacts    []excel.ContactRow
	sendResults []report.SendResult
	sentRows    []int
	waClient    *wa.Client
	sending     bool
}

// NewApp creates the application instance.
func NewApp() *App {
	return &App{}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	defaultMsg := loadDefaultMessage()
	s, _ := settings.Load(defaultMsg)
	a.settings = s

	client, err := wa.NewClient(a.handleSendEvent)
	if err == nil {
		a.waClient = client
	}
}

func loadDefaultMessage() string {
	// Dev: ../../shared/assets/default_message.txt relative to apps/go
	candidates := []string{
		filepath.Join("..", "..", "shared", "assets", "default_message.txt"),
	}
	if exe, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Join(filepath.Dir(exe), "assets", "default_message.txt"))
	}
	for _, p := range candidates {
		data, err := os.ReadFile(p)
		if err == nil {
			return string(data)
		}
	}
	return ""
}

func (a *App) handleSendEvent(evt wa.SendEvent) {
	if evt.Contact != nil && (evt.Status == wa.StatusSent || evt.Status == wa.StatusFailed || evt.Status == wa.StatusSkipped) {
		a.mu.Lock()
		a.sendResults = append(a.sendResults, report.NewResult(
			evt.Contact.Name,
			evt.Contact.PhoneNormalized,
			string(evt.Status),
			evt.Message,
		))
		if evt.Status == wa.StatusSent {
			a.sentRows = append(a.sentRows, evt.Contact.RowIndex)
		}
		a.mu.Unlock()
	}
	runtime.EventsEmit(a.ctx, "send-event", evt)
}

// GetSettings returns persisted settings for the UI.
func (a *App) GetSettings() settings.Settings {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.settings
}

// SaveSettings persists user preferences.
func (a *App) SaveSettings(s settings.Settings) error {
	a.mu.Lock()
	a.settings = s
	a.mu.Unlock()
	return settings.Save(s)
}

// PickExcel opens a file dialog and loads the selected workbook.
func (a *App) PickExcel() (map[string]any, error) {
	path, err := runtime.OpenFileDialog(a.ctx, runtime.OpenDialogOptions{
		Title: "Kies Excel-bestand",
		Filters: []runtime.FileFilter{
			{DisplayName: "Excel bestanden", Pattern: "*.xlsx"},
			{DisplayName: "Alle bestanden", Pattern: "*.*"},
		},
	})
	if err != nil || path == "" {
		return nil, err
	}

	sheets, err := excel.ListSheetNames(path)
	if err != nil {
		return nil, fmt.Errorf("kon Excel-bestand niet openen: %w", err)
	}
	if len(sheets) == 0 {
		return nil, fmt.Errorf("geen werkbladen gevonden in dit bestand")
	}

	a.mu.Lock()
	a.excelPath = path
	lastSheet := a.settings.LastSheet
	a.mu.Unlock()

	sheet := sheets[0]
	if lastSheet != "" {
		for _, s := range sheets {
			if s == lastSheet {
				sheet = s
				break
			}
		}
	}

	tableInfo, err := a.LoadSheet(sheet)
	if err != nil {
		return nil, err
	}
	tableInfo["path"] = path
	tableInfo["sheets"] = sheets
	return tableInfo, nil
}

// LoadSheet loads a worksheet and auto-detects columns.
func (a *App) LoadSheet(sheetName string) (map[string]any, error) {
	a.mu.Lock()
	path := a.excelPath
	s := a.settings
	a.mu.Unlock()

	if path == "" {
		return nil, fmt.Errorf("geen Excel-bestand geselecteerd")
	}

	table, err := excel.LoadSheetTable(path, sheetName)
	if err != nil {
		return nil, fmt.Errorf("kon werkblad niet laden: %w", err)
	}

	phoneGuess := excel.GuessPhoneColumn(table.Headers)
	phoneCol := phoneGuess
	if s.PhoneColumn != "" {
		for _, h := range table.Headers {
			if h == s.PhoneColumn {
				phoneCol = s.PhoneColumn
				break
			}
		}
	}
	if phoneCol == "" && len(table.Headers) > 0 {
		phoneCol = table.Headers[0]
	}

	nameCol := ""
	if s.NameColumn != "" {
		for _, h := range table.Headers {
			if h == s.NameColumn {
				nameCol = s.NameColumn
				break
			}
		}
	}
	if nameCol == "" {
		nameCol = excel.GuessNameColumn(table.Headers)
	}

	sentCol := ""
	if s.SentColumn != "" {
		for _, h := range table.Headers {
			if h == s.SentColumn {
				sentCol = s.SentColumn
				break
			}
		}
	}
	if sentCol == "" {
		sentCol = excel.GuessSentColumn(table.Headers)
	}

	a.mu.Lock()
	a.table = table
	a.mu.Unlock()

	count, err := a.RefreshContacts(phoneCol, nameCol, sentCol, s.CountryCode)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"headers":    table.Headers,
		"phoneCol":   phoneCol,
		"nameCol":    nameCol,
		"sentCol":    sentCol,
		"sheetName":  sheetName,
		"headerRow":  table.HeaderRow,
		"contactCount": count,
	}, nil
}

// RefreshContacts re-extracts contacts after column mapping changes.
func (a *App) RefreshContacts(phoneCol, nameCol, sentCol, countryCode string) (map[string]any, error) {
	a.mu.Lock()
	table := a.table
	skipSent := a.settings.SkipSent
	a.mu.Unlock()

	if table == nil {
		a.mu.Lock()
		a.contacts = nil
		a.mu.Unlock()
		return map[string]any{"total": 0, "alreadySent": 0, "remaining": 0, "contacts": []excel.ContactRow{}}, nil
	}

	if nameCol == "(geen)" {
		nameCol = ""
	}
	if sentCol == "(geen)" {
		sentCol = ""
	}
	if countryCode == "" {
		countryCode = "+31"
	}

	contacts := excel.ExtractContactsAll(table, phoneCol, nameCol, countryCode, sentCol)
	alreadySent := 0
	for _, c := range contacts {
		if c.AlreadySent {
			alreadySent++
		}
	}
	remaining := len(contacts)
	if sentCol != "" && skipSent {
		remaining = len(contacts) - alreadySent
	}

	a.mu.Lock()
	a.contacts = contacts
	a.mu.Unlock()

	return map[string]any{
		"total":       len(contacts),
		"alreadySent": alreadySent,
		"remaining":   remaining,
		"contacts":    contacts,
	}, nil
}

// PreviewMessage returns a personalized preview for the given template.
func (a *App) PreviewMessage(template string) map[string]string {
	a.mu.Lock()
	sample := message.PreviewSampleName
	if len(a.contacts) > 0 {
		sample = a.contacts[0].Name
	}
	a.mu.Unlock()
	return map[string]string{
		"name":    sample,
		"preview": message.Personalize(template, sample),
		"hint":    message.PlaceholderHint,
	}
}

// WhatsAppLoginStatus returns whether a session is active.
func (a *App) WhatsAppLoginStatus() map[string]any {
	if a.waClient == nil {
		return map[string]any{"loggedIn": false, "phone": ""}
	}
	loggedIn, _ := a.waClient.IsLoggedIn(a.ctx)
	phone := ""
	if loggedIn {
		phone = a.waClient.ConnectedPhone()
	}
	return map[string]any{"loggedIn": loggedIn, "phone": phone}
}

// WhatsAppPair starts QR pairing; QR codes are emitted as "qr-code" events
// containing a PNG data URL ready to render in an <img>.
func (a *App) WhatsAppPair() error {
	if a.waClient == nil {
		return fmt.Errorf("WhatsApp-client niet geïnitialiseerd")
	}
	return a.waClient.Pair(a.ctx, func(code string) {
		dataURL, err := qrDataURL(code)
		if err != nil {
			// Fall back to the raw payload so the user can still copy it.
			runtime.EventsEmit(a.ctx, "qr-code", map[string]string{"raw": code})
			return
		}
		runtime.EventsEmit(a.ctx, "qr-code", map[string]string{"image": dataURL, "raw": code})
	})
}

// qrDataURL renders a QR payload to a base64-encoded PNG data URL.
func qrDataURL(code string) (string, error) {
	png, err := qrcode.Encode(code, qrcode.Medium, 320)
	if err != nil {
		return "", err
	}
	return "data:image/png;base64," + base64.StdEncoding.EncodeToString(png), nil
}

// WhatsAppConnect reconnects an existing session.
func (a *App) WhatsAppConnect() error {
	if a.waClient == nil {
		return fmt.Errorf("WhatsApp-client niet geïnitialiseerd")
	}
	return a.waClient.Connect(a.ctx)
}

// WhatsAppLogout clears the paired session.
func (a *App) WhatsAppLogout() error {
	if a.waClient == nil {
		return nil
	}
	return a.waClient.Logout(a.ctx)
}

// StartSending begins a bulk send for the selected contact range.
func (a *App) StartSending(opts map[string]any) error {
	a.mu.Lock()
	if a.sending {
		a.mu.Unlock()
		return fmt.Errorf("verzenden is al bezig")
	}
	contacts := append([]excel.ContactRow(nil), a.contacts...)
	a.mu.Unlock()

	if len(contacts) == 0 {
		return fmt.Errorf("importeer eerst een Excel-bestand met telefoonnummers")
	}

	template, _ := opts["message"].(string)
	if strings.TrimSpace(template) == "" {
		return fmt.Errorf("voer eerst een bericht in")
	}

	waitTime := 15
	if v, ok := opts["waitTime"].(float64); ok {
		waitTime = int(v)
	}
	if waitTime < 5 {
		return fmt.Errorf("wachttijd moet minimaal 5 seconden zijn")
	}

	confirmEach := true
	if v, ok := opts["confirmEach"].(bool); ok {
		confirmEach = v
	}
	skipSent := true
	if v, ok := opts["skipSent"].(bool); ok {
		skipSent = v
	}

	startIdx := 0
	endIdx := len(contacts) - 1
	if v, ok := opts["startIndex"].(float64); ok {
		startIdx = int(v)
	}
	if v, ok := opts["endIndex"].(float64); ok {
		endIdx = int(v)
	}
	if endIdx < startIdx {
		return fmt.Errorf("ongeldig bereik")
	}

	toSend := contacts[startIdx : endIdx+1]
	if skipSent {
		filtered := make([]excel.ContactRow, 0, len(toSend))
		for _, c := range toSend {
			if !c.AlreadySent {
				filtered = append(filtered, c)
			}
		}
		toSend = filtered
	}
	if len(toSend) == 0 {
		return fmt.Errorf("geen contacten om te versturen in het gekozen bereik")
	}

	a.mu.Lock()
	a.sending = true
	a.sendResults = nil
	a.sentRows = nil
	a.mu.Unlock()

	go func() {
		defer func() {
			a.mu.Lock()
			a.sending = false
			a.mu.Unlock()
		}()
		a.waClient.SendBatch(a.ctx, toSend, template, waitTime, confirmEach)
	}()

	return nil
}

// StopSending requests the send loop to halt.
func (a *App) StopSending() {
	if a.waClient != nil {
		a.waClient.Stop()
	}
}

// ConfirmContinue resumes after per-message confirmation.
func (a *App) ConfirmContinue() {
	if a.waClient != nil {
		a.waClient.ConfirmContinue()
	}
}

// RecordSendResult stores a result from frontend event handling (optional helper).
func (a *App) RecordSendResult(name, phone, status, detail string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.sendResults = append(a.sendResults, report.NewResult(name, phone, status, detail))
}

// RecordSentRow tracks an Excel row for write-back.
func (a *App) RecordSentRow(rowIndex int) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.sentRows = append(a.sentRows, rowIndex)
}

// GetSendResults returns accumulated send results.
func (a *App) GetSendResults() []report.SendResult {
	a.mu.Lock()
	defer a.mu.Unlock()
	return append([]report.SendResult(nil), a.sendResults...)
}

// ExportReport saves send results to a CSV via file dialog.
func (a *App) ExportReport() (string, error) {
	a.mu.Lock()
	results := append([]report.SendResult(nil), a.sendResults...)
	a.mu.Unlock()

	if len(results) == 0 {
		return "", fmt.Errorf("er zijn nog geen verzendresultaten om te exporteren")
	}

	path, err := runtime.SaveFileDialog(a.ctx, runtime.SaveDialogOptions{
		Title:           "Rapport opslaan",
		DefaultFilename: "whatsapp_rapport.csv",
		Filters: []runtime.FileFilter{
			{DisplayName: "CSV-bestand", Pattern: "*.csv"},
		},
	})
	if err != nil || path == "" {
		return "", err
	}
	if err := report.Export(results, path); err != nil {
		return "", fmt.Errorf("kon rapport niet opslaan: %w", err)
	}
	return path, nil
}

// WriteBackSent marks sent rows in the Excel file.
func (a *App) WriteBackSent(sentCol string) (int, error) {
	a.mu.Lock()
	path := a.excelPath
	table := a.table
	rows := append([]int(nil), a.sentRows...)
	markSent := a.settings.MarkSent
	a.sentRows = nil
	a.mu.Unlock()

	if !markSent || sentCol == "" || sentCol == "(geen)" || len(rows) == 0 || path == "" || table == nil {
		return 0, nil
	}

	count, err := excel.MarkRowsSent(path, table.SheetName, sentCol, table.HeaderRow, rows)
	if err != nil {
		return 0, err
	}
	return count, nil
}

// SetExcelPath sets the workbook path when chosen externally.
func (a *App) SetExcelPath(path string) {
	a.mu.Lock()
	a.excelPath = path
	a.mu.Unlock()
}
