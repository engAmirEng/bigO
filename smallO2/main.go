package main

import (
	"fmt"
	"github.com/getsentry/sentry-go"
	"go.uber.org/zap"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

var (
	Release   = "1.0.0"
	BuildTime = "unknown"
)

var SupervisorXmlRpcClientType = 1

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--version" {
		fmt.Printf("Release: %s\nBuilt at: %s\n", Release, BuildTime)
		return
	} else if len(os.Args) > 1 && os.Args[1] == "--config" {
		configPath := os.Args[2]
		mainLoop(configPath)
	} else {
		fmt.Printf("unknown command %s\n", os.Args)
		return
	}
}

func mainLoop(configPath string) {
	config, err := loadConfig(configPath)
	if config.SentryDsn != nil {
		var environment string
		if config.IsDev {
			environment = "dev"
		} else {
			environment = "prod"
		}
		sentry.Init(sentry.ClientOptions{
			Dsn:         *config.SentryDsn,
			Release:     Release,
			Environment: environment,
		})

		defer sentry.Flush(time.Second * 3)
		defer sentry.Recover()
	}
	if err != nil {
		panic(fmt.Sprintf("Error loading config: %v", err))
	}
	logger := configureLogger(config)
	defer logger.Sync()
	defer func() {
		if r := recover(); r != nil {
			logger.Error("Recovered from panic", zap.Any("panic", r))
		}
	}()

	err = config.Validate()
	if err != nil {
		panic("could not validate config file at " + configPath + " " + err.Error())
	}
	supervisorXmlRpcClient, err := getSupervisorXmlRpcClient()
	defer supervisorXmlRpcClient.Close()

MainLoop:
	for {
		isSupervisorRunning := IsSupervisorRunning(supervisorXmlRpcClient)
		if isSupervisorRunning == false {
			logger.Warn("Supervisor not running")
			if config.FullControlSupervisord {
				supervisorDir, err := getSupervisorDir(config)
				if err != nil {
					panic(fmt.Sprintf("Error in getSupervisorDir: %v", err))
				}
				supervisorBaseConfigPath := filepath.Join(supervisorDir, "base_supervisor.conf")
				_, err = os.Stat(supervisorBaseConfigPath)
				if os.IsNotExist(err) {
					logger.Info(fmt.Sprintf("Creating supervisor base config at %v", supervisorBaseConfigPath))
					supervisorBaseConfigContent := getSupervisorBaseConfigContent(filepath.Join(supervisorDir, "supervisor.conf"))
					err = os.WriteFile(supervisorBaseConfigPath, []byte(supervisorBaseConfigContent), 0755)
					if err != nil {
						panic(fmt.Sprintf("panic in writing %s with %v", supervisorBaseConfigPath, err))
					}
				} else if err != nil {
					panic(fmt.Sprintf("panic in writing %s with %v", supervisorBaseConfigPath, err))
				}
				logger.Info("Starting Supervisor")
				supervisordCmd := exec.Command("supervisord", "-c", supervisorBaseConfigPath)
				_, err = supervisordCmd.Output()
				if err != nil {
					logger.Error(fmt.Sprintf("Error starting supervisor: %v", err))
				}
			} else {
				panic("supervisor is not running, start it !!!")
			}
		}

		supervisorXmlRpcClient, err = getSupervisorXmlRpcClient()
		payload, errors := getAPIRequest(config, supervisorXmlRpcClient)
		if len(errors) > 1 {
			for i, err := range errors {
				logger.Error(fmt.Sprintf("%ith Error in getting API request data: %v", i, err))
			}
		}

		response, err := makeSyncAPIRequest(config, payload)
		if err != nil {
			logger.Error(fmt.Sprintf("Error making API request: %v", err))
			time.Sleep(time.Second * time.Duration(config.IntervalSec))
			continue MainLoop
		}
		err = StatsCommitted(config)
		if err != nil {
			logger.Error(fmt.Sprintf("Error in StatsCommitted: %v", err))
		}
		err = response.Config.Validate()
		if err != nil {
			logger.Error(fmt.Sprintf("could not validate config form api %v", err))
		} else {
			config = response.Config
		}
		sentry.ConfigureScope(func(scope *sentry.Scope) {
			scope.SetTag("node_id", response.Runtime.NodeID)
			scope.SetTag("node_name", response.Runtime.NodeName)
		})
	FilesLoop:
		for _, fileInfo := range response.Files {
			_, err := os.Stat(fileInfo.DestPath)
			if os.IsNotExist(err) {
				if fileInfo.URL != nil {
					logger.Debug(fmt.Sprintf("start downloading file %v: %v", fileInfo.Hash, err))
					err := downloadAndVerifyFile(fileInfo, config)
					if err != nil {
						logger.Error(fmt.Sprintf("Error downloading file %v: %v", fileInfo.Hash, err))
						continue FilesLoop
					} else {
						logger.Debug(fmt.Sprintf("successfully downloaded %v", fileInfo.Hash))
					}
				} else if fileInfo.Content != nil {
					if err := os.MkdirAll(filepath.Dir(fileInfo.DestPath), 0755); err != nil {
						logger.Error(fmt.Sprintf("error in creating parent directories for %s", fileInfo.DestPath))
					}
					err = os.WriteFile(fileInfo.DestPath, []byte(*fileInfo.Content), os.FileMode(fileInfo.Permission))
					if err != nil {
						logger.Error(fmt.Sprintf("error in writing content for %s", fileInfo.DestPath))
					}
				} else {
					//it should be present all along
					logger.Debug(fmt.Sprintf("no url no content and no file for %s", fileInfo.DestPath))
				}
			} else if err != nil {
				logger.Error(fmt.Sprintf("Error is file stats checking for %s failed with %v", fileInfo.DestPath, err))
			}
		}
		supervisorDir, err := getSupervisorDir(config)
		if err != nil {
			panic(fmt.Sprintf("Error in getSupervisorDir: %v", err))
		}
		supervisorConfigPath := filepath.Join(supervisorDir, "supervisor.conf")
		currentSupervisorContentBytes, err := os.ReadFile(supervisorConfigPath)
		var currentSupervisorConfigContent string
		if err == nil {
			currentSupervisorConfigContent = string(currentSupervisorContentBytes)
		} else {
			if os.IsNotExist(err) {
				_, err = os.Create(supervisorConfigPath)
				if err != nil {
					panic(fmt.Sprintf("panic in touching %s with %v", supervisorConfigPath, err))
				} else {
					currentSupervisorConfigContent = ""
				}
			} else {
				panic(fmt.Sprintf("panic in reading %s with %v", supervisorConfigPath, err))
			}

		}
		newSupervisorConfigContent := response.SupervisorConfig.ConfigContent
		if removeComments(newSupervisorConfigContent) == removeComments(currentSupervisorConfigContent) {
			logger.Debug(fmt.Sprintf("already up to date."))
			time.Sleep(time.Second * time.Duration(config.IntervalSec))
			continue MainLoop
		}
		logger.Debug("update identified.")

		err = os.WriteFile(supervisorConfigPath, []byte(newSupervisorConfigContent), 0755)
		if err != nil {
			panic(fmt.Sprintf("panic in writing %s with %v", supervisorConfigPath, err))
		}

		var reloadConfigResult [][][]string
		err = supervisorXmlRpcClient.Call("supervisor.reloadConfig", nil, &reloadConfigResult)
		if err != nil {
			logger.Error(fmt.Sprintf("Error reloading supervisor config: %v", err))
			time.Sleep(time.Second * time.Duration(config.IntervalSec))
			continue MainLoop
		}
		added := reloadConfigResult[0][0]
		changed := reloadConfigResult[0][1]
		removed := reloadConfigResult[0][2]
		logger.Info(fmt.Sprintf("added %s changed %s remoded %s from supervisor", added, changed, removed))

		updateCmd := exec.Command("supervisorctl", "update")
		updateRes, err := updateCmd.Output()
		if err != nil {
			logger.Error(fmt.Sprintf("Error updating supervisor config: %v", err))
		}
		if updateRes != nil {
			logger.Info(fmt.Sprintf("supervisorctl updated result: %s", updateRes))
		}

		err = saveConfig(configPath, config)
		if err != nil {
			panic(fmt.Sprintf("Error saving updated config: %v", err))
		}

		time.Sleep(time.Second * time.Duration(config.IntervalSec))
	}
}
