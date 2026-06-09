package identity

import (
	"crypto/rand"
	"encoding/base64"
	"testing"
)

func TestCryptoRoundTrip(t *testing.T) {
	key := make([]byte, 32)
	_, _ = rand.Read(key)
	c, err := NewCrypto(base64.StdEncoding.EncodeToString(key))
	if err != nil {
		t.Fatalf("NewCrypto: %v", err)
	}
	plain := []byte("gho_exampletoken_1234567890")
	blob, err := c.Encrypt(plain)
	if err != nil {
		t.Fatalf("Encrypt: %v", err)
	}
	if string(blob) == string(plain) {
		t.Fatal("ciphertext equals plaintext")
	}
	got, err := c.Decrypt(blob)
	if err != nil {
		t.Fatalf("Decrypt: %v", err)
	}
	if string(got) != string(plain) {
		t.Fatalf("round trip mismatch: got %q want %q", got, plain)
	}
}

func TestCryptoRejectsBadKey(t *testing.T) {
	if _, err := NewCrypto("not-32-bytes"); err == nil {
		t.Fatal("expected error for short key")
	}
}
