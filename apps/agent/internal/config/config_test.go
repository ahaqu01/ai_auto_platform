package config

import "testing"

func TestValidate(t *testing.T) {
	cfg := Default()
	cfg.Server = "https://agent.example.com"
	cfg.Name = "local-01"
	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected valid config, got %v", err)
	}
}

func TestRejectsUnsafeConcurrency(t *testing.T) {
	cfg := Default()
	cfg.Server = "https://agent.example.com"
	cfg.Name = "local-01"
	cfg.MaxConcurrency = 0
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected validation error")
	}
}
