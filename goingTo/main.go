package main

import (
	"bigO/goingTo/configs"
	"flag"
	"fmt"
	"github.com/BurntSushi/toml"
	"log"
	"os"
	"time"
)

func main() {
	// Get config file path from command line argument
	configPath := flag.String("config", "", "Path to the configuration file")
	flag.Parse()

	if *configPath == "" {
		log.Fatal("Please provide the configuration file path using --config")
	}

	// Check if file exists
	if _, err := os.Stat(*configPath); os.IsNotExist(err) {
		log.Fatalf("Configuration file not found: %s", *configPath)
	}

	// Load configuration
	var config configs.Config
	if _, err := toml.DecodeFile(*configPath, &config); err != nil {
		log.Fatalf("Error loading configuration: %v", err)
	}

	// Display configuration
	fmt.Printf("Configuration Loaded:\n%+v\n", config)

	for {
		fmt.Printf("started")
		time.Sleep(time.Duration(config.Usage.Interval))
	}
}
