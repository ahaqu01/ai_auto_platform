package config

import (
	"errors"
	"time"
)

type Config struct {
	Server            string
	Name              string
	StateDir          string
	WorkDir           string
	MaxConcurrency    int
	HeartbeatInterval time.Duration
	PollTimeout       time.Duration
}

func Default() Config {
	return Config{
		StateDir:          "/var/lib/prexpand-agent",
		WorkDir:           "/var/lib/prexpand-agent/jobs",
		MaxConcurrency:    1,
		HeartbeatInterval: 15 * time.Second,
		PollTimeout:       30 * time.Second,
	}
}

func (c Config) Validate() error {
	if c.Server == "" {
		return errors.New("server is required")
	}
	if c.Name == "" {
		return errors.New("name is required")
	}
	if c.MaxConcurrency < 1 || c.MaxConcurrency > 32 {
		return errors.New("max concurrency must be between 1 and 32")
	}
	return nil
}
