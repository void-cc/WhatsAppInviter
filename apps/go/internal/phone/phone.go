package phone

import (
	"regexp"
	"strings"
)

var nonDigit = regexp.MustCompile(`\D`)

// Normalize converts a raw phone number to international format (+…).
func Normalize(raw, countryCode string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}

	clean := regexp.MustCompile(`[\s\-\(\)]`).ReplaceAllString(raw, "")
	if clean == "" {
		return ""
	}

	var digits string
	if strings.HasPrefix(clean, "+") {
		digits = "+" + nonDigit.ReplaceAllString(clean[1:], "")
	} else {
		digits = nonDigit.ReplaceAllString(clean, "")
	}

	if digits == "" || digits == "+" {
		return ""
	}

	cc := countryCode
	if !strings.HasPrefix(cc, "+") {
		cc = "+" + cc
	}

	if strings.HasPrefix(digits, "+") {
		return digits
	}
	if strings.HasPrefix(digits, "00") {
		return "+" + digits[2:]
	}
	if strings.HasPrefix(digits, "0") {
		return cc + digits[1:]
	}
	return cc + digits
}

// IsValid checks that a normalized number starts with + and has at least 10 digits.
func IsValid(normalized string) bool {
	if normalized == "" || !strings.HasPrefix(normalized, "+") {
		return false
	}
	count := 0
	for _, c := range normalized {
		if c >= '0' && c <= '9' {
			count++
		}
	}
	return count >= 10
}

// DigitsOnly strips the leading + for WhatsApp JID user part.
func DigitsOnly(normalized string) string {
	return strings.TrimPrefix(normalized, "+")
}
