package wa

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	waProto "go.mau.fi/whatsmeow/binary/proto"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"

	_ "modernc.org/sqlite"

	"github.com/void-cc/WhatsAppInviter/apps/go/internal/excel"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/message"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/phone"
	"github.com/void-cc/WhatsAppInviter/apps/go/internal/settings"
)

func sqliteDSN(path string) string {
	// modernc.org/sqlite uses _pragma=…, not mattn-style _foreign_keys=on.
	normalized := strings.ReplaceAll(path, "\\", "/")
	return fmt.Sprintf("file:%s?_pragma=foreign_keys(1)&_pragma=journal_mode(WAL)", normalized)
}

// SendStatus mirrors the Python sender statuses.
type SendStatus string

const (
	StatusSent            SendStatus = "SENT"
	StatusFailed          SendStatus = "FAILED"
	StatusSkipped         SendStatus = "SKIPPED"
	StatusWaitingConfirm  SendStatus = "WAITING_CONFIRM"
	StatusStopped         SendStatus = "STOPPED"
	StatusCompleted       SendStatus = "COMPLETED"
)

// SendEvent is emitted to the UI during a send run.
type SendEvent struct {
	Status  SendStatus        `json:"status"`
	Contact *excel.ContactRow `json:"contact,omitempty"`
	Index   int               `json:"index"`
	Total   int               `json:"total"`
	Message string            `json:"message"`
}

// EventHandler receives send lifecycle events.
type EventHandler func(SendEvent)

// Client wraps whatsmeow for pairing and bulk sending.
type Client struct {
	mu            sync.Mutex
	client        *whatsmeow.Client
	container     *sqlstore.Container
	dbPath        string
	onEvent       EventHandler
	stopRequested bool
	confirmCh     chan struct{}
}

// NewClient creates a WhatsApp client backed by a SQLite session store.
func NewClient(onEvent EventHandler) (*Client, error) {
	dbPath, err := settings.SessionDBPath()
	if err != nil {
		return nil, err
	}
	return &Client{
		dbPath:    dbPath,
		onEvent:   onEvent,
		confirmCh: make(chan struct{}, 1),
	}, nil
}

func (c *Client) ensureClient(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.client != nil {
		return nil
	}

	dbLog := waLog.Noop
	container, err := sqlstore.New(ctx, "sqlite", sqliteDSN(c.dbPath), dbLog)
	if err != nil {
		return fmt.Errorf("session store: %w", err)
	}
	deviceStore, err := container.GetFirstDevice(ctx)
	if err != nil {
		return fmt.Errorf("device store: %w", err)
	}

	client := whatsmeow.NewClient(deviceStore, waLog.Noop)
	c.container = container
	c.client = client
	return nil
}

// IsLoggedIn reports whether a paired session exists and is connected.
func (c *Client) IsLoggedIn(ctx context.Context) (bool, error) {
	if err := c.ensureClient(ctx); err != nil {
		return false, err
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.client.Store.ID != nil && c.client.IsConnected(), nil
}

// Connect connects an existing session without QR pairing.
func (c *Client) Connect(ctx context.Context) error {
	if err := c.ensureClient(ctx); err != nil {
		return err
	}
	c.mu.Lock()
	client := c.client
	c.mu.Unlock()

	if client.Store.ID == nil {
		return fmt.Errorf("geen gekoppelde sessie; scan eerst de QR-code")
	}
	if client.IsConnected() {
		return nil
	}
	return client.Connect()
}

// Pair starts QR pairing. onQR receives QR payload strings for display.
func (c *Client) Pair(ctx context.Context, onQR func(string)) error {
	if err := c.ensureClient(ctx); err != nil {
		return err
	}

	c.mu.Lock()
	client := c.client
	c.mu.Unlock()

	if client.Store.ID != nil {
		if !client.IsConnected() {
			return client.Connect()
		}
		return nil
	}

	qrChan, _ := client.GetQRChannel(ctx)
	if err := client.Connect(); err != nil {
		return fmt.Errorf("connect: %w", err)
	}

	for evt := range qrChan {
		switch evt.Event {
		case "code":
			if onQR != nil {
				onQR(evt.Code)
			}
		case "success":
			return nil
		case "timeout":
			return fmt.Errorf("QR-code verlopen; probeer opnieuw")
		}
	}
	return fmt.Errorf("QR-koppeling mislukt")
}

// Logout disconnects and clears the session.
func (c *Client) Logout(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.client != nil {
		if c.client.IsConnected() {
			_ = c.client.Logout(ctx)
		}
		c.client.Disconnect()
		c.client = nil
	}
	if c.container != nil {
		c.container = nil
	}
	return nil
}

// Stop requests the current send loop to halt.
func (c *Client) Stop() {
	c.mu.Lock()
	c.stopRequested = true
	c.mu.Unlock()
	select {
	case c.confirmCh <- struct{}{}:
	default:
	}
}

// ConfirmContinue resumes after per-message confirmation.
func (c *Client) ConfirmContinue() {
	select {
	case c.confirmCh <- struct{}{}:
	default:
	}
}

func (c *Client) emit(evt SendEvent) {
	if c.onEvent != nil {
		c.onEvent(evt)
	}
}

func phoneToJID(normalized string) (types.JID, error) {
	digits := phone.DigitsOnly(normalized)
	if digits == "" {
		return types.JID{}, fmt.Errorf("ongeldig nummer")
	}
	return types.NewJID(digits, types.DefaultUserServer), nil
}

// SendBatch sends personalized messages to contacts with optional confirmation pauses.
func (c *Client) SendBatch(ctx context.Context, contacts []excel.ContactRow, template string, waitTime int, confirmEach bool) {
	c.mu.Lock()
	c.stopRequested = false
	client := c.client
	c.mu.Unlock()

	if client == nil || client.Store.ID == nil {
		c.emit(SendEvent{
			Status:  StatusFailed,
			Message: "Niet ingelogd bij WhatsApp. Scan eerst de QR-code.",
		})
		return
	}
	if !client.IsConnected() {
		if err := client.Connect(); err != nil {
			c.emit(SendEvent{Status: StatusFailed, Message: fmt.Sprintf("Verbinden mislukt: %v", err)})
			return
		}
	}

	total := len(contacts)
	for i, contact := range contacts {
		c.mu.Lock()
		stopped := c.stopRequested
		c.mu.Unlock()
		if stopped {
			c.emit(SendEvent{
				Status:  StatusStopped,
				Contact: &contact,
				Index:   i,
				Total:   total,
				Message: "Gestopt door gebruiker.",
			})
			return
		}

		jid, err := phoneToJID(contact.PhoneNormalized)
		if err != nil {
			c.emit(SendEvent{
				Status:  StatusFailed,
				Contact: &contact,
				Index:   i + 1,
				Total:   total,
				Message: fmt.Sprintf("Fout bij %s: %v", contact.PhoneNormalized, err),
			})
			continue
		}

		// Pre-check WhatsApp registration
		checks, err := client.IsOnWhatsApp(ctx, []string{"+" + phone.DigitsOnly(contact.PhoneNormalized)})
		if err == nil && len(checks) > 0 && !checks[0].IsIn {
			c.emit(SendEvent{
				Status:  StatusSkipped,
				Contact: &contact,
				Index:   i + 1,
				Total:   total,
				Message: fmt.Sprintf("Overgeslagen %s (%s): geen WhatsApp-account", contact.PhoneNormalized, contact.Name),
			})
		} else {
			text := message.Personalize(template, contact.Name)
			msg := &waProto.Message{Conversation: proto.String(text)}
			_, err = client.SendMessage(ctx, jid, msg)
			if err != nil {
				c.emit(SendEvent{
					Status:  StatusFailed,
					Contact: &contact,
					Index:   i + 1,
					Total:   total,
					Message: fmt.Sprintf("Fout bij %s: %v", contact.PhoneNormalized, err),
				})
			} else {
				c.emit(SendEvent{
					Status:  StatusSent,
					Contact: &contact,
					Index:   i + 1,
					Total:   total,
					Message: fmt.Sprintf("Verzonden naar %s (%s)", contact.PhoneNormalized, contact.Name),
				})
			}
		}

		c.mu.Lock()
		stopped = c.stopRequested
		c.mu.Unlock()
		if stopped {
			c.emit(SendEvent{
				Status:  StatusStopped,
				Contact: &contact,
				Index:   i + 1,
				Total:   total,
				Message: "Gestopt door gebruiker.",
			})
			return
		}

		if i < total-1 {
			if confirmEach {
				c.emit(SendEvent{
					Status:  StatusWaitingConfirm,
					Contact: &contact,
					Index:   i + 1,
					Total:   total,
					Message: "Wacht op bevestiging voor volgende bericht…",
				})
				select {
				case <-ctx.Done():
					c.emit(SendEvent{Status: StatusStopped, Message: "Gestopt."})
					return
				case <-c.confirmCh:
					c.mu.Lock()
					stopped = c.stopRequested
					c.mu.Unlock()
					if stopped {
						c.emit(SendEvent{Status: StatusStopped, Message: "Gestopt door gebruiker."})
						return
					}
				}
			} else if waitTime > 0 {
				time.Sleep(time.Duration(waitTime) * time.Second)
			} else {
				time.Sleep(2 * time.Second)
			}
		}
	}

	c.emit(SendEvent{
		Status:  StatusCompleted,
		Index:   total,
		Total:   total,
		Message: "Alle berichten verwerkt.",
	})
}

// ConnectedPhone returns a human-readable linked account id when available.
func (c *Client) ConnectedPhone() string {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.client == nil || c.client.Store.ID == nil {
		return ""
	}
	user := c.client.Store.ID.User
	if user == "" {
		return ""
	}
	if strings.HasPrefix(user, "+") {
		return user
	}
	return "+" + user
}
