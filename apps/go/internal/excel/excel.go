package excel

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/xuri/excelize/v2"

	"github.com/void-cc/WhatsAppInviter/apps/go/internal/message"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/phone"
)

var (
	phoneHeaderPatterns = []string{
		`mobiel\s*telefoon`, `telefoonnummer`, `telefoon`, `mobiel`, `gsm`, `phone`, `mobile`, `cell`,
	}
	nameHeaderPatterns = []string{
		`volledige\s*naam`, `naam`, `name`, `student`, `voornaam`,
	}
	sentHeaderPatterns = []string{
		`bericht\s*verzonden`, `uitnodiging\s*verzonden`, `verzonden`, `verstuurd`,
		`uitgenodigd`, `invited`, `sent`,
	}
	truthy = map[string]struct{}{
		"true": {}, "waar": {}, "ja": {}, "yes": {}, "y": {}, "1": {}, "x": {},
		"✓": {}, "✔": {}, "v": {}, "done": {}, "ok": {}, "verzonden": {}, "verstuurd": {},
	}
)

// ContactRow is one importable contact.
type ContactRow struct {
	PhoneRaw        string `json:"phoneRaw"`
	PhoneNormalized string `json:"phoneNormalized"`
	Name            string `json:"name"`
	RowIndex        int    `json:"rowIndex"`
	AlreadySent     bool   `json:"alreadySent"`
}

// SheetTable holds parsed sheet data.
type SheetTable struct {
	SheetName  string              `json:"sheetName"`
	Headers    []string            `json:"headers"`
	HeaderRow  int                 `json:"headerRow"`
	Rows       []map[string]string `json:"rows"`
	RowNumbers []int               `json:"rowNumbers"`
}

func cellValue(v any) string {
	if v == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(v))
}

func scoreHeader(header string, patterns []string) int {
	headerLower := strings.ToLower(header)
	best := 0
	for _, pattern := range patterns {
		re := regexp.MustCompile(pattern)
		if re.MatchString(headerLower) {
			if len(pattern) > best {
				best = len(pattern)
			}
		}
	}
	return best
}

func detectHeaderRow(sheet *excelize.Rows, maxScan int) (int, []string, error) {
	bestRow := 0
	bestCount := 0
	var bestHeaders []string

	rowIdx := 0
	for sheet.Next() {
		rowIdx++
		if rowIdx > maxScan {
			break
		}
		cols, err := sheet.Columns()
		if err != nil {
			return 0, nil, err
		}
		var headers []string
		for _, v := range cols {
			if t := cellValue(v); t != "" {
				headers = append(headers, t)
			}
		}
		if len(headers) >= 2 && len(headers) > bestCount {
			bestCount = len(headers)
			bestRow = rowIdx
			bestHeaders = headers
		}
	}
	if bestRow == 0 {
		return 0, nil, fmt.Errorf("could not detect a table header in this sheet")
	}
	return bestRow, bestHeaders, nil
}

// ListSheetNames returns workbook sheet names.
func ListSheetNames(path string) ([]string, error) {
	f, err := excelize.OpenFile(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return f.GetSheetList(), nil
}

// LoadSheetTable reads one sheet into a SheetTable.
func LoadSheetTable(path, sheetName string) (*SheetTable, error) {
	f, err := excelize.OpenFile(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	if idx, _ := f.GetSheetIndex(sheetName); idx == 0 {
		return nil, fmt.Errorf("sheet '%s' not found in workbook", sheetName)
	}

	rows, err := f.Rows(sheetName)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	headerRow, headers, err := detectHeaderRow(rows, 20)
	if err != nil {
		return nil, err
	}

	// Re-open rows to read data after header
	rows.Close()
	rows, err = f.Rows(sheetName)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tableRows []map[string]string
	var rowNumbers []int
	rowIdx := 0
	for rows.Next() {
		rowIdx++
		if rowIdx <= headerRow {
			continue
		}
		cols, err := rows.Columns()
		if err != nil {
			return nil, err
		}
		rowData := make(map[string]string)
		hasData := false
		for i, header := range headers {
			val := ""
			if i < len(cols) {
				val = cellValue(cols[i])
			}
			rowData[header] = val
			if val != "" {
				hasData = true
			}
		}
		if hasData {
			tableRows = append(tableRows, rowData)
			rowNumbers = append(rowNumbers, rowIdx)
		}
	}

	return &SheetTable{
		SheetName:  sheetName,
		Headers:    headers,
		HeaderRow:  headerRow,
		Rows:       tableRows,
		RowNumbers: rowNumbers,
	}, nil
}

// GuessPhoneColumn auto-detects the phone column header.
func GuessPhoneColumn(headers []string) string {
	return guessColumn(headers, phoneHeaderPatterns, nil)
}

// GuessNameColumn auto-detects the name column header.
func GuessNameColumn(headers []string) string {
	skip := append(phoneHeaderPatterns, sentHeaderPatterns...)
	return guessColumn(headers, nameHeaderPatterns, skip)
}

// GuessSentColumn auto-detects the sent-status column header.
func GuessSentColumn(headers []string) string {
	return guessColumn(headers, sentHeaderPatterns, phoneHeaderPatterns)
}

func guessColumn(headers, patterns, skipPatterns []string) string {
	bestHeader := ""
	bestScore := 0
	for _, header := range headers {
		if len(skipPatterns) > 0 && scoreHeader(header, skipPatterns) > 0 {
			continue
		}
		score := scoreHeader(header, patterns)
		if score > bestScore {
			bestScore = score
			bestHeader = header
		}
	}
	return bestHeader
}

// ParseBool interprets Excel checkbox / truthy cell values.
func ParseBool(value string) bool {
	text := strings.ToLower(strings.TrimSpace(value))
	if text == "" {
		return false
	}
	_, ok := truthy[text]
	return ok
}

// ExtractContacts builds contact rows from a loaded table.
func ExtractContacts(table *SheetTable, phoneColumn, nameColumn, countryCode, sentColumn string, skipSent bool) []ContactRow {
	seen := make(map[string]struct{})
	var contacts []ContactRow

	for i, row := range table.Rows {
		rowNumber := table.RowNumbers[i]
		raw := row[phoneColumn]
		if raw == "" {
			continue
		}
		normalized := phone.Normalize(raw, countryCode)
		if normalized == "" || !phone.IsValid(normalized) {
			continue
		}
		if _, dup := seen[normalized]; dup {
			continue
		}
		seen[normalized] = struct{}{}

		name := message.FallbackName
		if nameColumn != "" {
			if n := strings.TrimSpace(row[nameColumn]); n != "" {
				name = n
			}
		}

		alreadySent := false
		if sentColumn != "" {
			alreadySent = ParseBool(row[sentColumn])
		}
		if skipSent && alreadySent {
			continue
		}

		contacts = append(contacts, ContactRow{
			PhoneRaw:        raw,
			PhoneNormalized: normalized,
			Name:            name,
			RowIndex:        rowNumber,
			AlreadySent:     alreadySent,
		})
	}
	return contacts
}

// ExtractContactsAll includes already-sent rows (for counting); filtering happens at send time.
func ExtractContactsAll(table *SheetTable, phoneColumn, nameColumn, countryCode, sentColumn string) []ContactRow {
	seen := make(map[string]struct{})
	var contacts []ContactRow

	for i, row := range table.Rows {
		rowNumber := table.RowNumbers[i]
		raw := row[phoneColumn]
		if raw == "" {
			continue
		}
		normalized := phone.Normalize(raw, countryCode)
		if normalized == "" || !phone.IsValid(normalized) {
			continue
		}
		if _, dup := seen[normalized]; dup {
			continue
		}
		seen[normalized] = struct{}{}

		name := message.FallbackName
		if nameColumn != "" {
			if n := strings.TrimSpace(row[nameColumn]); n != "" {
				name = n
			}
		}

		alreadySent := false
		if sentColumn != "" {
			alreadySent = ParseBool(row[sentColumn])
		}

		contacts = append(contacts, ContactRow{
			PhoneRaw:        raw,
			PhoneNormalized: normalized,
			Name:            name,
			RowIndex:        rowNumber,
			AlreadySent:     alreadySent,
		})
	}
	return contacts
}

// MarkRowsSent writes TRUE into the sent column for given Excel row numbers.
func MarkRowsSent(path, sheetName, columnHeader string, headerRow int, rowNumbers []int) (int, error) {
	if len(rowNumbers) == 0 {
		return 0, nil
	}

	f, err := excelize.OpenFile(path)
	if err != nil {
		return 0, err
	}
	defer f.Close()

	colIdx := 0
	cols, err := f.GetCols(sheetName)
	if err != nil {
		return 0, err
	}
	for i, col := range cols {
		if len(col) >= headerRow && cellValue(col[headerRow-1]) == columnHeader {
			colIdx = i + 1
			break
		}
	}
	if colIdx == 0 {
		return 0, fmt.Errorf("column '%s' not found in header row", columnHeader)
	}

	colName, err := excelize.ColumnNumberToName(colIdx)
	if err != nil {
		return 0, err
	}

	for _, rowNum := range rowNumbers {
		cell := fmt.Sprintf("%s%d", colName, rowNum)
		if err := f.SetCellValue(sheetName, cell, true); err != nil {
			return 0, err
		}
	}

	if err := f.Save(); err != nil {
		return 0, err
	}
	return len(rowNumbers), nil
}
