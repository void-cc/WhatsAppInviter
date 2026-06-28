package report

import (
	"encoding/csv"
	"fmt"
	"os"
	"time"
)

// SendResult is one row in the export CSV.
type SendResult struct {
	Timestamp string `json:"timestamp"`
	Name      string `json:"name"`
	Phone     string `json:"phone"`
	Status    string `json:"status"`
	Detail    string `json:"detail"`
}

// NewResult creates a result with the current timestamp.
func NewResult(name, phone, status, detail string) SendResult {
	return SendResult{
		Timestamp: time.Now().Format("2006-01-02 15:04:05"),
		Name:      name,
		Phone:     phone,
		Status:    status,
		Detail:    detail,
	}
}

// Export writes send results to a UTF-8-BOM semicolon-separated CSV (Excel-friendly).
func Export(results []SendResult, path string) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()

	// UTF-8 BOM
	if _, err := f.Write([]byte{0xEF, 0xBB, 0xBF}); err != nil {
		return err
	}

	w := csv.NewWriter(f)
	w.Comma = ';'
	if err := w.Write([]string{"Tijdstip", "Naam", "Telefoonnummer", "Status", "Details"}); err != nil {
		return err
	}
	for _, r := range results {
		if err := w.Write([]string{r.Timestamp, r.Name, r.Phone, r.Status, r.Detail}); err != nil {
			return err
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		return fmt.Errorf("csv flush: %w", err)
	}
	return nil
}
