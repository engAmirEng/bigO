package main

import (
	"bigO/goingTo/configs"
	"bigO/goingTo/xray"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/BurntSushi/toml"
	"go.uber.org/zap"
	"io"
	"net/http"
	"os"
	"time"
)

func main() {
	// Get config file path from command line argument
	configPath := flag.String("config", "", "Path to the configuration file")
	flag.Parse()
	logger := configureLogger()
	defer logger.Sync()
	output := configureOutput()
	defer output.Sync()
	defer func() {
		if r := recover(); r != nil {
			logger.Error("Recovered from panic", zap.Any("panic", r))
		}
	}()

	if *configPath == "" {
		panic("Please provide the configuration file path using --config")
	}

	if _, err := os.Stat(*configPath); os.IsNotExist(err) {
		panic(fmt.Sprintf("Configuration file not found: %s", *configPath))
	}

	var config configs.Config
	if _, err := toml.DecodeFile(*configPath, &config); err != nil {
		panic(fmt.Sprintf("Error loading configuration: %v", err))
	}

	logger.Debug(fmt.Sprintf("Configuration Loaded:\n%+v\n", config))

	var xrayapi *xray.XrayAPI
	if config.Xray.Usage != nil && config.Xray.APIHost != "" && config.Xray.APIPort != 0 {
		xrayapi = &xray.XrayAPI{}
		logger.Info("initializing Xray API")
		err := xrayapi.Init(config.Xray.APIPort)
		defer xrayapi.Close()
		if err != nil {
			panic(fmt.Sprintf("error in initializing xrayapi: %v", err))
		}
	}

	for {
		logger.Debug("getting usage")
		DoTrafficStats(xrayapi, &config, output, logger)
		DoMetrics(&config, output, logger)
		time.Sleep(time.Duration(config.Xray.Usage.Interval) * time.Second)
	}
}

func DoTrafficStats(x *xray.XrayAPI, config *configs.Config, output *zap.Logger, logger *zap.Logger) {
	if config.Xray.Usage != nil {
		if x == nil {
			logger.Error("xrayapi is not initialized")
			return
		}
	} else {
		logger.Info("skipping trafficstats")
		return
	}
	rawTraffic, err := x.GetTrafficRaw(config.Xray.Usage.Reset, logger)
	if err != nil {
		logger.Error("Error getting raw traffic", zap.Error(err))
	}
	if len(rawTraffic) == 0 {
		logger.Error("no traffic")
		return
	}

	var stats = make([]Stat, len(rawTraffic))
	for _, stat := range rawTraffic {
		if stat.Value == 0 || stat.Name == "" {
			continue
		}
		stats = append(stats, Stat{
			Name:  stat.Name,
			Value: stat.Value,
		})
	}
	result := Result{
		Stats: stats,
	}
	jsonResult, err := json.Marshal(result)
	if err != nil {
		panic(fmt.Sprintf("error in marshalling raw trafic to json: %v", err))
	}
	output.Info(string(jsonResult), zap.String("result_type", "xray_raw_traffic_v1"))
}

func DoMetrics(config *configs.Config, output *zap.Logger, logger *zap.Logger) {
	if config.Xray.Metrics != nil {
		if config.Xray.MetricsUrl == "" {
			logger.Error("MetricsUrl is nil")
			return
		}
	} else {
		logger.Info("skipping metrics")
		return
	}

	req, err := http.NewRequest("GET", config.Xray.MetricsUrl, nil)
	if err != nil {
		logger.Error("Error calling metrics", zap.Error(err))
		return
	}
	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		logger.Error("Error calling metrics", zap.Error(err))
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		logger.Error(fmt.Sprint("Error metrics response code is %d", resp.StatusCode))
		return
	}
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		logger.Error("Error in reading metrics", zap.Error(err))
		return
	}
	output.Info(string(bodyBytes), zap.String("result_type", "xray_raw_metrics_v1"))
}
