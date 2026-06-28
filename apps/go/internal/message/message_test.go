package message_test

import (
	"testing"

	"github.com/void-cc/WhatsAppInviter/apps/go/internal/message"
)

func TestPersonalizeVoornaam(t *testing.T) {
	got := message.Personalize("Hoi {voornaam}!", "Jan Jansen")
	want := "Hoi Jan!"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestPersonalizeNaam(t *testing.T) {
	got := message.Personalize("Beste {naam}", "Jan Jansen")
	want := "Beste Jan Jansen"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestFirstNameCommaStyle(t *testing.T) {
	got := message.FirstName("Jansen, Jan")
	if got != "Jan" {
		t.Fatalf("got %q want Jan", got)
	}
}
