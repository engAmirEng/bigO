package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/pelletier/go-toml/v2"
)

type Config struct {
	SyncURL     string `toml:"sync_url"`
	APIKey      string `toml:"api_key"`
	IntervalSec int    `toml:"interval_sec"`
}

type FileSchema struct {
	DestPath   string `json:"dest_path"`
	Content    string `json:"content"`
	URL        string `json:"url"`
	Permission int    `json:"permission"`
}

type SupervisorConfig struct {
	ConfigContent string `toml:"config_content"`
}

// APIResponse represents the response from the server
type APIResponse struct {
	supervisor_config SupervisorConfig `json:"supervisor_config"`
	Files             []FileSchema     `json:"files"`
	Config            Config           `json:"config"`
}

func main() {
	configPath := "config.toml"

	for {
		// Load config
		config, err := loadConfig(configPath)
		if err != nil {
			fmt.Printf("Error loading config: %v\n", err)
			time.Sleep(time.Second * 10) // Wait before retrying
			continue
		}

		// Make API request
		response, err := makeAPIRequest(config)
		if err != nil {
			fmt.Printf("Error making API request: %v\n", err)
			time.Sleep(time.Second * time.Duration(config.IntervalSec))
			continue
		}

		// Process files
		for _, fileInfo := range response.Files {
			err := downloadAndVerifyFile(fileInfo)
			if err != nil {
				fmt.Printf("Error processing file %s: %v\n", fileInfo.Filename, err)
				continue
			}
			fmt.Printf("Successfully processed file: %s\n", fileInfo.Filename)
		}

		// Update config with new values
		err = saveConfig(configPath, response.UpdatedConfig)
		if err != nil {
			fmt.Printf("Error saving updated config: %v\n", err)
		}

		// Wait for the next interval
		time.Sleep(time.Second * time.Duration(config.IntervalSec))
	}
}

func loadConfig(path string) (Config, error) {
	var config Config

	data, err := os.ReadFile(path)
	if err != nil {
		return config, fmt.Errorf("failed to read config file: %w", err)
	}

	err = toml.Unmarshal(data, &config)
	if err != nil {
		return config, fmt.Errorf("failed to parse config file: %w", err)
	}

	return config, nil
}

func saveConfig(path string, config Config) error {
	data, err := toml.Marshal(config)
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	err = os.WriteFile(path, data, 0644)
	if err != nil {
		return fmt.Errorf("failed to write config file: %w", err)
	}

	return nil
}

func makeAPIRequest(config Config) (APIResponse, error) {
	var response APIResponse

	// Create request payload (adjust as needed)
	payload := map[string]string{
		"api_key": config.APIKey,
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return response, fmt.Errorf("failed to marshal request payload: %w", err)
	}

	// Make the POST request
	req, err := http.NewRequest("POST", config.ServerBaseURL, bytes.NewBuffer(payloadBytes))
	if err != nil {
		return response, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return response, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return response, fmt.Errorf("server returned non-OK status: %s", resp.Status)
	}

	// Parse the response
	err = json.NewDecoder(resp.Body).Decode(&response)
	if err != nil {
		return response, fmt.Errorf("failed to decode response: %w", err)
	}

	return response, nil
}

func downloadAndVerifyFile(fileInfo FileInfo) error {
	// Create temp file
	tempDir := os.TempDir()
	tempFilePath := filepath.Join(tempDir, fileInfo.Filename+".tmp")

	tempFile, err := os.Create(tempFilePath)
	if err != nil {
		return fmt.Errorf("failed to create temp file: %w", err)
	}
	defer tempFile.Close()

	// Download the file
	resp, err := http.Get(fileInfo.URL)
	if err != nil {
		return fmt.Errorf("failed to start download: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("server returned non-OK status: %s", resp.Status)
	}

	// Create hash calculator
	hasher := sha256.New()

	// Download and write file in chunks
	buffer := make([]byte, 32*1024) // 32KB chunks

	for {
		bytesRead, err := resp.Body.Read(buffer)
		if err != nil && err != io.EOF {
			return fmt.Errorf("error reading from response: %w", err)
		}

		if bytesRead > 0 {
			// Write to file
			_, err = tempFile.Write(buffer[:bytesRead])
			if err != nil {
				return fmt.Errorf("error writing to temp file: %w", err)
			}

			// Update hash
			_, err = hasher.Write(buffer[:bytesRead])
			if err != nil {
				return fmt.Errorf("error updating hash: %w", err)
			}
		}

		if err == io.EOF {
			break
		}
	}

	// Close the file to ensure all data is written
	tempFile.Close()

	// Verify hash
	calculatedHash := hex.EncodeToString(hasher.Sum(nil))
	if calculatedHash != fileInfo.SHA256 {
		// Remove temp file if hash doesn't match
		os.Remove(tempFilePath)
		return fmt.Errorf("hash verification failed: expected %s, got %s", fileInfo.SHA256, calculatedHash)
	}

	// Move temp file to final destination
	finalPath := filepath.Join("downloads", fileInfo.Filename)

	// Ensure directory exists
	err = os.MkdirAll(filepath.Dir(finalPath), 0755)
	if err != nil {
		return fmt.Errorf("failed to create destination directory: %w", err)
	}

	err = os.Rename(tempFilePath, finalPath)
	if err != nil {
		return fmt.Errorf("failed to move file to final destination: %w", err)
	}

	return nil
}
