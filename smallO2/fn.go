package main

import (
	"alexejk.io/go-xmlrpc"
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"github.com/pelletier/go-toml/v2"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"gopkg.in/natefinch/lumberjack.v2"
	"io"
	"io/fs"
	"log"
	"math"
	"math/rand"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
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

func configureLogger(stdout bool, config Config) *zap.Logger {
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
	if config.IsDev || stdout {
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

	if len(config.SyncURLSpecs) == 0 {
		if config.SyncURL == "" {
			config.SyncURL = os.Getenv("sync_url")
		}
		if config.SyncURL != "" {
			config.SyncURLSpecs = append(config.SyncURLSpecs, UrlSpec{URL: config.SyncURL, ProxyUrl: os.Getenv("proxy_url"), Weight: 1})
		}
	}
	if len(config.SyncURLSpecs) == 1 {
		config.SyncURLSpecs[0].Weight = 1
	}

	if config.APIKey == "" {
		config.APIKey = os.Getenv("api_key")
	}
	if config.IntervalSec == 0 {
		intervalSecStr := os.Getenv("interval_sec")
		intervalSec, err := strconv.Atoi(intervalSecStr)
		if err == nil {
			config.IntervalSec = intervalSec
		}
	}
	if config.WorkingDir == "" {
		config.WorkingDir = os.Getenv("working_dir")
	}
	if config.SentryDsn == nil {
		sentryDsn := os.Getenv("sentry_dsn")
		if sentryDsn != "" {
			config.SentryDsn = &sentryDsn
		}
	}
	if config.FullControlSupervisord == false {
		fullControlSupervisordStr := os.Getenv("full_control_supervisord")
		fullControlSupervisord, err := strconv.ParseBool(fullControlSupervisordStr)
		if err == nil {
			config.FullControlSupervisord = fullControlSupervisord
		}
	}
	if config.SupervisorBaseConfigPath == "" {
		config.SupervisorBaseConfigPath = os.Getenv("supervisor_base_config_path")
	}
	if config.SafeStatsSize == 0 {
		SafeStatsSizeStr := os.Getenv("safe_stats_size")
		SafeStatsSize, err := strconv.Atoi(SafeStatsSizeStr)
		if err == nil {
			config.SafeStatsSize = SafeStatsSize
		}
		if config.SafeStatsSize == 0 {
			config.SafeStatsSize = 10_000_000
		}
	}
	if config.EachCollectionSize == 0 {
		EachCollectionSizeStr := os.Getenv("each_collection_size")
		EachCollectionSize, err := strconv.Atoi(EachCollectionSizeStr)
		if err == nil {
			config.EachCollectionSize = EachCollectionSize
		}
		if config.EachCollectionSize == 0 {
			config.EachCollectionSize = 4_000_000
		}
	}

	return config, nil
}

func (c Config) Validate() error {
	for i, syncURLSpec := range c.SyncURLSpecs {
		if syncURLSpec.URL == "" {
			return fmt.Errorf("sync url at index %d not set", i)
		}
	}
	if len(c.SyncURLSpecs) == 0 {
		return fmt.Errorf("sync url not set")
	}

	if c.APIKey == "" {
		return fmt.Errorf("API key not set")
	}
	if c.WorkingDir == "" {
		return fmt.Errorf("working directory not set")
	}
	if c.FullControlSupervisord {
		if c.SupervisorBaseConfigPath == "" {
			return fmt.Errorf("supervisor base config path not set")
		}
		_, err := os.Stat(c.SupervisorBaseConfigPath)
		if os.IsNotExist(err) {
			return fmt.Errorf("path %s does not exist for supervisor base config path", c.SupervisorBaseConfigPath)
		} else if err != nil {
			return fmt.Errorf("supervisor base config path stats error: %w", err)
		}
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
		supervisorXmlRpcClient, err = xmlrpc.NewClient("http://dummy/RPC2", xmlrpc.HttpClient(&http.Client{Transport: UnixStreamTransport}))
	} else {
		supervisorXmlRpcClient, err = xmlrpc.NewClient("http://127.0.0.1:9002/RPC2", nil)
	}
	if err != nil {
		panic(fmt.Sprintf("Error instantiating supervisor rpc client: %v", err))
	}
	return supervisorXmlRpcClient, nil
}
func IsSupervisorRunning(supervisorXmlRpcClient *xmlrpc.Client) (bool, error) {
	result := struct {
		Result struct {
			Statecode int    `xmlrpc:"statecode"`
			Statename string `xmlrpc:"statename"`
		}
	}{}

	err := supervisorXmlRpcClient.Call("supervisor.getState", nil, &result)
	if err != nil {
		return false, err
	}
	return true, nil
}
func getAPIRequest(config Config, supervisorXmlRpcClient *xmlrpc.Client) (*APIRequest, func() error, []error) {
	var apiRequest = APIRequest{}
	var errors []error
	apiRequest.Config = config

	var configsStates []ConfigStateSchema
	err, StatsCommitted := getConfigsStates(&configsStates, config, supervisorXmlRpcClient)
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

	return &apiRequest, StatsCommitted, nil
}

func getConfigsStates(configsStates *[]ConfigStateSchema, config Config, supervisorXmlRpcClient *xmlrpc.Client) (error, func() error) {
	SupervisorProcessInfosDummy := struct {
		SupervisorProcessInfos []SupervisorProcessInfoSchema
	}{
		SupervisorProcessInfos: nil,
	}
	var currentConfigsStates []ConfigStateSchema
	var includedBackfilePaths []string
	err := supervisorXmlRpcClient.Call("supervisor.getAllProcessInfo", nil, &SupervisorProcessInfosDummy)
	if err != nil {
		return fmt.Errorf("failed to get process info: %w", err), nil
	}
	supervisorProcessInfos := SupervisorProcessInfosDummy.SupervisorProcessInfos
	safeStatsSize := config.SafeStatsSize
	//safeStatsGage := 5_000_000
	eachCollectionSize := config.EachCollectionSize
	hasClearedAnyLogs := false
	now := time.Now()
	currentFilepath, saveStatsBackUp, getOnCommit := getStatsBackUpProcedure(config, now)
	defer func(stats *[]ConfigStateSchema, hasClearedAnyLogs *bool, collectTime time.Time) {
		if *hasClearedAnyLogs == false {
			return
		}
		saveStatsBackUp(stats)
	}(&currentConfigsStates, &hasClearedAnyLogs, time.Now().UTC())

	//safeSizePassed := false
	currentByteSize := 0
ProcessInfoLoop:
	for _, supervisorProcessInfo := range supervisorProcessInfos {
		collectionSize := eachCollectionSize
		if supervisorProcessInfo.StateName != "RUNNING" {
			// since it cannot be cleared so we end up sending it over and over
			// https://github.com/Supervisor/supervisor/issues/804
			collectionSize = int(math.Round(float64(eachCollectionSize) * 0.1))
		}
		TailProcessStdoutLogResultDummy := struct {
			TailProcessStdoutLogResult []interface{}
		}{}
		err = supervisorXmlRpcClient.Call("supervisor.tailProcessStdoutLog", struct {
			DumParam1 string
			DumParam2 int
			DumParam3 int
		}{
			DumParam1: supervisorProcessInfo.Name,
			DumParam2: 0,
			DumParam3: collectionSize,
		}, &TailProcessStdoutLogResultDummy)
		if err != nil {
			return fmt.Errorf("failed to tail process stdout: %w", err), getOnCommit(includedBackfilePaths)
		}
		tailProcessStdoutLogResult := TailProcessStdoutLogResultDummy.TailProcessStdoutLogResult
		if tailProcessStdoutLogResult[0] == nil {
			tailProcessStdoutLogResult[0] = ""
		}
		TailProcessStderrLogResultDummy := struct {
			TailProcessStderrLogResult []interface{}
		}{}
		err = supervisorXmlRpcClient.Call("supervisor.tailProcessStderrLog", struct {
			DumParam1 string
			DumParam2 int
			DumParam3 int
		}{
			DumParam1: supervisorProcessInfo.Name,
			DumParam2: 0,
			DumParam3: collectionSize,
		}, &TailProcessStderrLogResultDummy)
		if err != nil {
			return fmt.Errorf("failed to tail process stdout: %w", err), getOnCommit(includedBackfilePaths)
		}
		tailProcessStderrLogResult := TailProcessStderrLogResultDummy.TailProcessStderrLogResult
		if tailProcessStderrLogResult[0] == nil {
			tailProcessStderrLogResult[0] = ""
		}

		stdoutContent := tailProcessStdoutLogResult[0].(string)
		stdoutOByteSize := len(stdoutContent)
		stderrContent := tailProcessStderrLogResult[0].(string)
		stderrByteSize := len(stderrContent)

		if currentByteSize+stdoutOByteSize+stderrByteSize > safeStatsSize {
			//safeSizePassed = true
			break ProcessInfoLoop
		}
		ClearSuccessDummy := struct {
			ClearSuccess bool
		}{}
		err = supervisorXmlRpcClient.Call("supervisor.clearProcessLogs", struct {
			DumParam1 string
		}{
			DumParam1: supervisorProcessInfo.Name,
		}, &ClearSuccessDummy)
		clearSuccess := ClearSuccessDummy.ClearSuccess
		if err != nil || clearSuccess == false {
			return fmt.Errorf("failed to clear process logs: %w", err), getOnCommit(includedBackfilePaths)
		}
		hasClearedAnyLogs = true

		configStateSchema := ConfigStateSchema{
			Time:                  now,
			SupervisorProcessInfo: supervisorProcessInfo,
			Stdout: SupervisorProcessTailLogSerializerSchema{
				Bytes:    stdoutContent,
				Offset:   tailProcessStdoutLogResult[1].(int),
				Overflow: tailProcessStdoutLogResult[2].(bool),
			},
			Stderr: SupervisorProcessTailLogSerializerSchema{
				Bytes:    stderrContent,
				Offset:   tailProcessStderrLogResult[1].(int),
				Overflow: tailProcessStderrLogResult[2].(bool),
			},
		}
		currentConfigsStates = append(currentConfigsStates, configStateSchema)
		currentByteSize += stdoutOByteSize + stderrByteSize
	}
	var pervConfigStats []ConfigStateSchema
	remainedSize := safeStatsSize - currentByteSize
	if remainedSize > 0 {
		includedBackfilePaths = loadBackedConfigStats(&pervConfigStats, config, remainedSize, []string{currentFilepath})
	}

	*configsStates = append(*configsStates, currentConfigsStates...)
	*configsStates = append(*configsStates, pervConfigStats...)
	return nil, getOnCommit(includedBackfilePaths)
}

func loadBackedConfigStats(configStates *[]ConfigStateSchema, config Config, maxSize int, excludeFileoaths []string) []string {
	dir := getLogsDir(config)
	pattern := regexp.MustCompile(`^configs_states_bak_(\d{4})_(\d{2})_(\d{2})_(\d{2})(\d{2})(\d{2})\.json$`)

	var backfiles []backFileInfo

	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			panic(err)
		}

		if d.IsDir() {
			return nil
		}

		fileName := d.Name()
		matches := pattern.FindStringSubmatch(fileName)
		if matches != nil {
			// Parse timestamp from filename
			timestampStr := fmt.Sprintf("%s-%s-%sT%s:%s:%sZ",
				matches[1], matches[2], matches[3],
				matches[4], matches[5], matches[6])
			timestamp, err := time.Parse(time.RFC3339, timestampStr)
			if err != nil {
				return err
			}

			// Get file size
			info, err := d.Info()
			if err != nil {
				panic(err)
			}

			backfiles = append(backfiles, backFileInfo{
				path: path,
				size: int(info.Size()),
				time: timestamp,
			})
		}
		return nil
	})

	if err != nil {
		panic(err)
	}

	sort.Slice(backfiles, func(i, j int) bool {
		return backfiles[i].time.After(backfiles[j].time)
	})

	occupiedSize := 0
	var includedBackfilePaths []string
	for _, backfile := range backfiles {
		var currentConfigStates []ConfigStateSchema
		remaizedSize := maxSize - occupiedSize
		if Contains(excludeFileoaths, backfile.path) {
			continue
		}
		if backfile.size == 0 {
			continue
		}
		if backfile.size > remaizedSize {
			continue
		}
		data, err := os.ReadFile(backfile.path)
		if err != nil {
			panic(err)
		}
		err = json.Unmarshal(data, &currentConfigStates)
		if err != nil {
			panic(err)
		}
		*configStates = append(*configStates, currentConfigStates...)
		occupiedSize += backfile.size
		includedBackfilePaths = append(includedBackfilePaths, backfile.path)
	}
	return includedBackfilePaths
}

func getStatsBackUpProcedure(config Config, time time.Time) (string, func(stats *[]ConfigStateSchema), func([]string) func() error) {
	filename := fmt.Sprintf("configs_states_bak_%04d_%02d_%02d_%02d%02d%02d.json",
		time.Year(), time.Month(), time.Day(),
		time.Hour(), time.Minute(), time.Second(),
	)
	filePath := filepath.Join(getLogsDir(config), filename)
	save := func(stats *[]ConfigStateSchema) {
		data, err := json.Marshal(stats)
		if err != nil {
			panic(fmt.Sprintf("failed to marshal config: %s", err))
		}
		err = os.WriteFile(filePath, data, 0644)
		if err != nil {
			panic(fmt.Errorf("failed to write config file: %w", err))
		}
	}
	getOnCommit := func(includedBackfilePaths []string) func() error {
		commit := func() error {
			err := os.Remove(filePath)
			if err != nil {
				return fmt.Errorf("failed to delete latest config stats backup file: %w", err)
			}
			for _, path := range includedBackfilePaths {
				err := os.Remove(path)
				if err != nil {
					return fmt.Errorf("failed to delete %s config stats backup file: %w", path, err)
				}
			}
			return nil

		}
		return commit
	}

	return filePath, save, getOnCommit
}

func makeSyncAPIRequest(config Config, payload *APIRequest, logger *zap.Logger) (*APIResponse, *[]byte, error) {
	var response APIResponse
	var loggingDebounce float64 = 3

	var urlChoices []struct {
		url      string
		proxyUrl string
	}
	for _, spec := range config.SyncURLSpecs {
		for i := 0; i < spec.Weight; i++ {
			urlChoices = append(urlChoices, struct{ url, proxyUrl string }{url: spec.URL, proxyUrl: spec.ProxyUrl})
		}
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return &response, nil, fmt.Errorf("failed to marshal request payload: %w", err)
	}
	err = os.WriteFile(filepath.Join(config.WorkingDir, "sync_request.txt"), payloadBytes, 0644)

	var proxyURL *url.URL
	var Url string
	tries := 0
	logTries := 0
	var lastLog time.Time
	rand.Seed(time.Now().UnixNano())
	for {
		urlChoice := urlChoices[rand.Intn(len(urlChoices))]
		if urlChoice.proxyUrl != "" {
			proxyURL, err = url.Parse(urlChoice.proxyUrl)
			if err != nil {
				logger.Warn("failed to parse proxy url", zap.String("url", urlChoice.url), zap.Error(err))
				continue
			}
		} else {
			proxyURL = nil
		}
		Url = urlChoice.url
		payloadBuffer := bytes.NewBuffer(payloadBytes)
		req, err := http.NewRequest("POST", Url, payloadBuffer)
		if err != nil {
			return &response, nil, fmt.Errorf("failed to create request: %w", err)
		}

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Api-Key "+config.APIKey)
		req.Header.Set("User-Agent", fmt.Sprintf("smallO2:%v", Release))

		transport := &http.Transport{
			Proxy: http.ProxyURL(proxyURL),
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
			proxyPartMsg := ""
			if proxyURL != nil {
				proxyPartMsg = ": " + proxyURL.String()
			}
			lastLogDiff := time.Now().Sub(lastLog)
			if lastLogDiff.Seconds() > loggingDebounce {
				logger.Warn(fmt.Sprintf("Failed to send request to %s%s for %d times", Url, proxyPartMsg, logTries), zap.Error(err))
				lastLog = time.Now()
				logTries = 0
			}

			//if netErr, ok := err.(net.Error); ok {
			//if opErr, ok := err.(*net.OpError); ok {
			if true {
				tries++
				logTries++
				time.Sleep(500 * time.Millisecond)
				continue
			}
			return &response, nil, fmt.Errorf("failed to send request with %s tries: %w", tries, err)
		}
		defer resp.Body.Close()

		if resp.StatusCode == http.StatusOK {
			// Parse the response
			err = json.NewDecoder(resp.Body).Decode(&response)
			if err != nil {
				return &response, nil, fmt.Errorf("failed to decode response: %w", err)
			}
			return &response, nil, nil
		}
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return &response, nil, fmt.Errorf("server returned non-OK status: %s; additionally, failed to read response body: %v", resp.Status, err)
		}
		bodyRunes := []rune(string(bodyBytes))
		bodyString := string(bodyRunes[:min(len(bodyRunes), 50)])
		return &response, &bodyBytes, fmt.Errorf("server returned non-OK status: %s; response body: %s", resp.Status, bodyString)
	}
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
		return fmt.Errorf("sha missmatch happened for %s", *fileInfo.Hash)
	}

	perm := os.FileMode(fileInfo.Permission)
	out, err := os.OpenFile(fileInfo.DestPath, os.O_RDWR|os.O_CREATE|os.O_TRUNC, perm)

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

func Contains(slice []string, str string) bool {
	for _, s := range slice {
		if s == str {
			return true
		}
	}
	return false
}
