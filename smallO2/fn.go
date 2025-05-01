package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"github.com/kolo/xmlrpc"
	"github.com/pelletier/go-toml/v2"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gopkg.in/natefinch/lumberjack.v2"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func getLogsDir(config Config) string {
	logsDir := filepath.Join(config.WorkingDir, "logs")
	if err := os.MkdirAll(logsDir, 0755); err != nil {
		panic(fmt.Sprintf("error in creating logs directory in %s", logsDir))
	}
	return logsDir
}

func configureLogger(config Config) *zap.Logger {
	fileWriter := &lumberjack.Logger{
		Filename:   filepath.Join(getLogsDir(config), "app.log"), // <-- Path to your log file
		MaxSize:    50,                                           // megabytes
		MaxBackups: 0,                                            // number of backups
		Compress:   false,                                        // gzip compress backups
	}

	fileWriterSyncer := zapcore.AddSync(fileWriter)
	consoleSyncer := zapcore.AddSync(os.Stdout)

	encoderCfg := zap.NewProductionEncoderConfig()
	encoderCfg.TimeKey = "timestamp"
	encoderCfg.EncodeTime = zapcore.ISO8601TimeEncoder

	var core zapcore.Core
	if config.IsDev {
		core = zapcore.NewTee(
			zapcore.NewCore(zapcore.NewJSONEncoder(encoderCfg), consoleSyncer, zap.DebugLevel),
			zapcore.NewCore(zapcore.NewJSONEncoder(encoderCfg), fileWriterSyncer, zap.DebugLevel),
		)
	} else {
		core = zapcore.NewCore(zapcore.NewJSONEncoder(encoderCfg), fileWriterSyncer, zap.DebugLevel)
	}

	logger := zap.New(core)
	return logger
}

func getSupervisorDir(config Config) (string, error) {
	res := filepath.Join(config.WorkingDir, "supervisor")
	if err := os.MkdirAll(res, 0755); err != nil {
		return res, err
	}
	return res, nil
}

func getSupervisorBaseConfigContent(supervisorConfigPath string) string {
	template := `
; supervisor config file

[unix_http_server]
file=/var/run/supervisor.sock   ; (the path to the socket file)
chmod=0700                       ; sockef file mode (default 0700)

[supervisord]
logfile=/var/log/supervisor/supervisord.log ; (main log file;default $CWD/supervisord.log)
pidfile=/var/run/supervisord.pid ; (supervisord pidfile;default supervisord.pid)
childlogdir=/var/log/supervisor            ; ('AUTO' child log dir, default $TEMP)

; the below section must remain in the config file for RPC
; (supervisorctl/web interface) to work, additional interfaces may be
; added by defining them in separate rpcinterface: sections
[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock ; use a unix:// URL  for a unix socket

; The [include] section can just contain the "files" setting.  This
; setting can list multiple files (separated by whitespace or
; newlines).  It can also contain wildcards.  The filenames are
; interpreted as relative to this file.  Included files *cannot*
; include files themselves.

[include]
files = %s
`
	return fmt.Sprintf(template, supervisorConfigPath)
}

func removeComments(input string) string {
	var output strings.Builder
	scanner := bufio.NewScanner(strings.NewReader(input))

	for scanner.Scan() {
		line := scanner.Text()
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, ";") {
			continue
		}
		output.WriteString(line + "\n")
	}

	return output.String()
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

func (c Config) Validate() error {
	if c.SyncURL == "" {
		return fmt.Errorf("sync url not set")
	}
	if c.APIKey == "" {
		return fmt.Errorf("API key not set")
	}
	if c.WorkingDir == "" {
		return fmt.Errorf("working directory not set")
	}
	return nil
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
func getSupervisorXmlRpcClient() (*xmlrpc.Client, error) {
	var supervisorXmlRpcClient *xmlrpc.Client
	var err error
	if SupervisorXmlRpcClientType == 1 {
		supervisorXmlRpcUnixAddr := "/var/run/supervisor.sock"
		UnixStreamTransport := &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				return (&net.Dialer{}).DialContext(ctx, "unix", supervisorXmlRpcUnixAddr)
			},
		}
		supervisorXmlRpcClient, err = xmlrpc.NewClient("http://dummy/RPC2", UnixStreamTransport)
	} else {
		supervisorXmlRpcClient, err = xmlrpc.NewClient("http://127.0.0.1:9002/RPC2", nil)
	}
	if err != nil {
		panic(fmt.Sprintf("Error instantiating supervisor rpc client: %v", err))
	}
	return supervisorXmlRpcClient, nil
}
func IsSupervisorRunning(supervisorXmlRpcClient *xmlrpc.Client) bool {
	supervisorStateInfos := struct {
		Statecode int    `xmlrpc:"statecode"`
		Statename string `xmlrpc:"statename"`
	}{}
	err := supervisorXmlRpcClient.Call("supervisor.getState", nil, &supervisorStateInfos)
	if err != nil {
		return false
	}
	return true
}
func getAPIRequest(config Config, supervisorXmlRpcClient *xmlrpc.Client) (*APIRequest, []error) {
	var apiRequest = APIRequest{}
	var errors []error
	apiRequest.Config = config

	var configsStates []ConfigStateSchema
	err := getConfigsStates(&configsStates, config, supervisorXmlRpcClient)
	if err != nil {
		errors = append(errors, fmt.Errorf("Error getting API request data: %v", err))
	}
	apiRequest.ConfigsStates = configsStates

	//todo
	apiRequest.SelfLogs = SupervisorProcessTailLogSerializerSchema{Bytes: "fdfd", Offset: 0, Overflow: false}

	ipaCmd := exec.Command("ip", "a")
	ipaRes, err := ipaCmd.Output()
	if err != nil {
		errors = append(errors, fmt.Errorf("error in getting 'ip a':: %w", err))
	}
	apiRequest.Metrics = MetricSchema{IPA: string(ipaRes)}

	return &apiRequest, nil
}

func getConfigsStates(configsStates *[]ConfigStateSchema, config Config, supervisorXmlRpcClient *xmlrpc.Client) error {
	var supervisorProcessInfos []SupervisorProcessInfoSchema
	err := supervisorXmlRpcClient.Call("supervisor.getAllProcessInfo", nil, &supervisorProcessInfos)
	if err != nil {
		return fmt.Errorf("failed to get process info: %w", err)
	}

	loadBackedConfigStats(configsStates, config)
	hasClearedAnyLogs := false
	defer func(stats *[]ConfigStateSchema, hasClearedAnyLogs *bool) {
		if *hasClearedAnyLogs == false {
			return
		}
		saveStatsBackUp(configsStates, config)
	}(configsStates, &hasClearedAnyLogs)
	now := time.Now()
	for _, supervisorProcessInfo := range supervisorProcessInfos {
		var tailProcessStdoutLogResult []interface{}
		err = supervisorXmlRpcClient.Call("supervisor.tailProcessStdoutLog", []interface{}{supervisorProcessInfo.Name, 0, 20_000_000}, &tailProcessStdoutLogResult)
		if err != nil {
			return fmt.Errorf("failed to tail process stdout: %w", err)
		}
		if tailProcessStdoutLogResult[0] == nil {
			tailProcessStdoutLogResult[0] = ""
		}

		var tailProcessStderrLogResult []interface{}
		err = supervisorXmlRpcClient.Call("supervisor.tailProcessStderrLog", []interface{}{supervisorProcessInfo.Name, 0, 20_000_000}, &tailProcessStderrLogResult)
		if err != nil {
			return fmt.Errorf("failed to tail process stdout: %w", err)
		}
		if tailProcessStderrLogResult[0] == nil {
			tailProcessStderrLogResult[0] = ""
		}

		err = supervisorXmlRpcClient.Call("supervisor.clearProcessLogs", []interface{}{supervisorProcessInfo.Name}, nil)
		if err != nil {
			return fmt.Errorf("failed to clear process logs: %w", err)
		}
		hasClearedAnyLogs = true

		configStateSchema := ConfigStateSchema{
			Time:                  now,
			SupervisorProcessInfo: supervisorProcessInfo,
			Stdout: SupervisorProcessTailLogSerializerSchema{
				Bytes:    tailProcessStdoutLogResult[0].(string),
				Offset:   tailProcessStdoutLogResult[1].(int64),
				Overflow: tailProcessStdoutLogResult[2].(bool),
			},
			Stderr: SupervisorProcessTailLogSerializerSchema{
				Bytes:    tailProcessStderrLogResult[0].(string),
				Offset:   tailProcessStderrLogResult[1].(int64),
				Overflow: tailProcessStderrLogResult[2].(bool),
			},
		}
		*configsStates = append(*configsStates, configStateSchema)
	}
	return nil
}

func loadBackedConfigStats(configStates *[]ConfigStateSchema, config Config) {
	data, err := os.ReadFile(filepath.Join(getLogsDir(config), "configs_states.json.bak"))
	if err != nil {
		if os.IsNotExist(err) {
			return
		}
		panic(fmt.Sprintf("failed to read config stats backup file: %s", err))
	}

	if len(data) == 0 {
		return
	}
	err = json.Unmarshal(data, configStates)
	if err != nil {
		panic(fmt.Sprintf("failed to parse config stats backup file: %s", err))
	}
}

func saveStatsBackUp(stats *[]ConfigStateSchema, config Config) {
	// saving response.ConfigsStates as json for the next request
	data, err := json.Marshal(stats)
	if err != nil {
		panic(fmt.Sprintf("failed to marshal config: %s", err))
	}

	err = os.WriteFile(filepath.Join(getLogsDir(config), "configs_states.json.bak"), data, 0644)
	if err != nil {
		panic(fmt.Errorf("failed to write config file: %w", err))
	}
}

func StatsCommitted(config Config) error {
	err := os.Truncate(filepath.Join(getLogsDir(config), "configs_states.json.bak"), 0)
	if err != nil {
		return fmt.Errorf("failed to enpty config stats backup file: %w", err)
	}
	return nil
}

func makeSyncAPIRequest(config Config, payload *APIRequest) (*APIResponse, *[]byte, error) {
	var response APIResponse

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return &response, nil, fmt.Errorf("failed to marshal request payload: %w", err)
	}

	// Make the POST request
	req, err := http.NewRequest("POST", config.SyncURL, bytes.NewBuffer(payloadBytes))
	if err != nil {
		return &response, nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Api-Key "+config.APIKey)
	req.Header.Set("User-Agent", fmt.Sprintf("smallO2:%v", Release))

	transport := &http.Transport{
		DialContext: (&net.Dialer{
			Timeout: 2 * time.Second,
		}).DialContext,
		TLSHandshakeTimeout:   5 * time.Second,
		ResponseHeaderTimeout: 15 * time.Second,
	}

	client := &http.Client{Transport: transport}
	if config.IsDev {
		client.Timeout = 600 * time.Second
	}
	resp, err := client.Do(req)
	if err != nil {
		return &response, nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return &response, nil, fmt.Errorf("server returned non-OK status: %s; additionally, failed to read response body: %v", resp.Status, err)
		}
		return &response, &bodyBytes, fmt.Errorf("server returned non-OK status: %s; response body: %s", resp.Status, string(bodyBytes)[:50])
	}

	// Parse the response
	err = json.NewDecoder(resp.Body).Decode(&response)
	if err != nil {
		return &response, nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &response, nil, nil
}

func downloadAndVerifyFile(fileInfo FileSchema, config Config) error {
	// Ensure dest paths exists for early return
	destPathDir := filepath.Dir(fileInfo.DestPath)
	err := os.MkdirAll(destPathDir, 0755)
	if err != nil {
		return fmt.Errorf("failed to create destination directory at %s: %v", destPathDir, err)
	}

	// Create temp file
	tempDir := os.TempDir()
	fileName := filepath.Base(fileInfo.DestPath)
	tempFilePath := filepath.Join(tempDir, fileName+".tmp")

	tempFile, err := os.Create(tempFilePath)
	if err != nil {
		return fmt.Errorf("failed to create temp file: %w", err)
	}
	defer tempFile.Close()

	// Download the file
	req, err := http.NewRequest("GET", *fileInfo.URL, nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", "Api-Key "+config.APIKey)
	req.Header.Set("User-Agent", fmt.Sprintf("smallO2:%v", Release))

	client := &http.Client{}
	resp, err := client.Do(req)
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

	// Verify hash
	calculatedHash := hex.EncodeToString(hasher.Sum(nil))
	if calculatedHash != *fileInfo.Hash {
		// Remove temp file if hash doesn't match
		os.Remove(tempFilePath)
		return fmt.Errorf("sha missmatch happened for %s", fileInfo.Hash)
	}

	out, err := os.Create(fileInfo.DestPath)
	if err != nil {
		return fmt.Errorf("failed to create destination file: %w", err)
	}
	defer out.Close()

	in, err := os.Open(tempFilePath)
	if err != nil {
		log.Fatalf("Failed to open source file: %v", err)
	}
	defer out.Close()

	if _, err = io.Copy(out, in); err != nil {
		return fmt.Errorf("failed to copy temp file to destination file: %w", err)
	}

	//err = os.Rename(tempFilePath, fileInfo.DestPath)
	//if err != nil {
	//	return fmt.Errorf("failed to move file to final destination: %w", err)
	//}
	return nil
}
