package settings

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
)

// Settings mirrors the Python app's persisted preferences.
type Settings struct {
	Message       string `json:"message"`
	CountryCode   string `json:"country_code"`
	WaitTime      int    `json:"wait_time"`
	ConfirmEach   bool   `json:"confirm_each"`
	PhoneColumn   string `json:"phone_column"`
	NameColumn    string `json:"name_column"`
	SentColumn    string `json:"sent_column"`
	LastSheet     string `json:"last_sheet"`
	Appearance    string `json:"appearance"`
	SkipSent      bool   `json:"skip_sent"`
	MarkSent      bool   `json:"mark_sent"`
	ReducedMotion *bool  `json:"reduced_motion"`
}

func defaultSettings(defaultMessage string) Settings {
	rm := OSPrefersReducedMotion()
	return Settings{
		Message:       defaultMessage,
		CountryCode:   "+31",
		WaitTime:      15,
		ConfirmEach:   true,
		Appearance:    "Systeem",
		SkipSent:      true,
		MarkSent:      true,
		ReducedMotion: &rm,
	}
}

// AppDataDir returns the per-user config directory.
func AppDataDir() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		home, herr := os.UserHomeDir()
		if herr != nil {
			return "", err
		}
		dir = home
	}
	return filepath.Join(dir, "WhatsAppInviter"), nil
}

func settingsPath() (string, error) {
	base, err := AppDataDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "settings.json"), nil
}

// OSPrefersReducedMotion reads the Windows accessibility animation setting when available.
func OSPrefersReducedMotion() bool {
	if runtime.GOOS != "windows" {
		return false
	}
	// Best-effort: without registry access in pure Go we default to false on dev builds.
	return false
}

// Load reads settings from disk, falling back to defaults.
func Load(defaultMessage string) (Settings, error) {
	s := defaultSettings(defaultMessage)
	path, err := settingsPath()
	if err != nil {
		return s, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			if s.Message == "" {
				s.Message = defaultMessage
			}
			return s, nil
		}
		return s, err
	}
	if err := json.Unmarshal(data, &s); err != nil {
		return defaultSettings(defaultMessage), nil
	}
	if s.Message == "" {
		s.Message = defaultMessage
	}
	if s.ReducedMotion == nil {
		rm := OSPrefersReducedMotion()
		s.ReducedMotion = &rm
	}
	return s, nil
}

// Save persists settings to disk.
func Save(s Settings) error {
	path, err := settingsPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

// SessionDBPath returns the whatsmeow SQLite session file path.
func SessionDBPath() (string, error) {
	base, err := AppDataDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(base, "whatsapp_session.db"), nil
}
