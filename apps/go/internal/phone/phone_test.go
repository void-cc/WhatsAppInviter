package phone_test

import (
	"testing"

	"github.com/void-cc/WhatsAppInviter/apps/go/internal/phone"
)

func TestNormalizeDutchMobile(t *testing.T) {
	got := phone.Normalize("0612345678", "+31")
	want := "+31612345678"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestNormalizeInternational(t *testing.T) {
	got := phone.Normalize("+31612345678", "+31")
	if got != "+31612345678" {
		t.Fatalf("got %q", got)
	}
}

func TestIsValid(t *testing.T) {
	if !phone.IsValid("+31612345678") {
		t.Fatal("expected valid")
	}
	if phone.IsValid("+123") {
		t.Fatal("expected invalid")
	}
}
