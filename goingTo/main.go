package main

import (
	"bigO/goingTo/configs"
	"bigO/goingTo/xray"
	"encoding/json"
	"flag"
	"fmt"
	"github.com/BurntSushi/toml"
	"go.uber.org/zap"
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
	xrayapi := xray.XrayAPI{}
	err := xrayapi.Init(config.Xray.APIPort)
	defer xrayapi.Close()
	if err != nil {
		panic(fmt.Sprintf("error in initializing xrayapi: %v", err))
	}
	for {
		logger.Debug("getting usage")
		DoTrafficStats(&xrayapi, &config, output, logger)
		time.Sleep(time.Duration(config.Xray.Usage.Interval) * time.Second)
	}
}

func DoTrafficStats(x *xray.XrayAPI, config *configs.Config, output *zap.Logger, logger *zap.Logger) {
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
