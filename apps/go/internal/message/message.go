package message

import (
	"regexp"
	"strings"
)

const (
	PlaceholderHint   = "Gebruik {voornaam} of {naam} om het bericht te personaliseren."
	FallbackName      = "student"
	PreviewSampleName = "Jan Jansen"
)

var (
	reVoornaam = regexp.MustCompile(`(?i)\{\s*voornaam\s*\}`)
	reNaam     = regexp.MustCompile(`(?i)\{\s*naam\s*\}`)
)

// FirstName returns the first word of a name, handling "Achternaam, Voornaam" style.
func FirstName(fullName string) string {
	cleaned := strings.TrimSpace(fullName)
	if cleaned == "" {
		return ""
	}
	if idx := strings.Index(cleaned, ","); idx >= 0 {
		after := strings.TrimSpace(cleaned[idx+1:])
		if after != "" {
			cleaned = after
		}
	}
	parts := strings.Fields(cleaned)
	if len(parts) == 0 {
		return ""
	}
	return parts[0]
}

// Personalize replaces {naam}/{voornaam} placeholders (case-insensitive).
func Personalize(message, name string) string {
	if message == "" {
		return message
	}

	full := strings.TrimSpace(name)
	fname := FirstName(full)

	nameRepl := full
	if nameRepl == "" {
		nameRepl = FallbackName
	}
	firstRepl := fname
	if firstRepl == "" {
		if full != "" {
			firstRepl = full
		} else {
			firstRepl = FallbackName
		}
	}

	result := reVoornaam.ReplaceAllString(message, firstRepl)
	result = reNaam.ReplaceAllString(result, nameRepl)
	return result
}
