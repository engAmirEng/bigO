package main

import (
	"fmt"
	"github.com/getsentry/sentry-go"
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
		panic(fmt.Sprintf("Error loading config: %v\n", err))
	}
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
			fmt.Printf("Supervisor not running\n")
			if config.FullControlSupervisord {
				supervisorBaseConfigPath := filepath.Join(getSupervisorDir(config), "base_supervisor.conf")
				_, err := os.Stat(supervisorBaseConfigPath)
				if os.IsNotExist(err) {
					fmt.Printf("Creating supervisor base config at %s\n", supervisorBaseConfigPath)
					supervisorBaseConfigContent := getSupervisorBaseConfigContent(filepath.Join(getSupervisorDir(config), "supervisor.conf"))
					err = os.WriteFile(supervisorBaseConfigPath, []byte(supervisorBaseConfigContent), 0755)
					if err != nil {
						panic(fmt.Sprintf("panic in writing %s with %v", supervisorBaseConfigPath, err))
					}
				} else if err != nil {
					panic(fmt.Sprintf("panic in writing %s with %v", supervisorBaseConfigPath, err))
				}
				fmt.Printf("Starting Supervisor\n")
				supervisordCmd := exec.Command("supervisord", "-c", supervisorBaseConfigPath)
				_, err = supervisordCmd.Output()
				if err != nil {
					fmt.Printf("Error starting supervisor: %v\n", err)
				}
			} else {
				panic("supervisor is not running, start it !!!\n")
			}
		}

		supervisorXmlRpcClient, err = getSupervisorXmlRpcClient()
		payload, err := getAPIRequest(config, supervisorXmlRpcClient)
		if err != nil {
			fmt.Printf("Error getting API request data: %v\n", err)
		}

		response, err := makeSyncAPIRequest(config, payload)
		if err != nil {
			fmt.Printf("Error making API request: %v\n", err)
			time.Sleep(time.Second * time.Duration(config.IntervalSec))
			continue MainLoop
		}
		err = response.Config.Validate()
		if err != nil {
			fmt.Printf("could not validate config form api %v", err)
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
					fmt.Printf("start downloading file %v: %v\n", fileInfo.Hash, err)
					err := downloadAndVerifyFile(fileInfo, config)
					if err != nil {
						fmt.Printf("Error downloading file %v: %v\n", fileInfo.Hash, err)
						continue FilesLoop
					} else {
						fmt.Printf("successfully downloaded %v\n", fileInfo.Hash)
					}
				} else if fileInfo.Content != nil {
					if err := os.MkdirAll(filepath.Dir(fileInfo.DestPath), 0755); err != nil {
						fmt.Printf("error in creating parent directories for %s\n", fileInfo.DestPath)
					}
					err = os.WriteFile(fileInfo.DestPath, []byte(*fileInfo.Content), os.FileMode(fileInfo.Permission))
					if err != nil {
						fmt.Printf("error in writing content for %s\n", fileInfo.DestPath)
					}
				} else {
					//it should be present all along
					fmt.Printf("no url no content and no file for %s\n", fileInfo.DestPath)
				}
			} else if err != nil {
				fmt.Printf("Error is file stats checking for %v\n", fileInfo.DestPath, err)
			}
		}

		supervisorConfigPath := filepath.Join(getSupervisorDir(config), "supervisor.conf")
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
			fmt.Println("already up to date.")
			time.Sleep(time.Second * time.Duration(config.IntervalSec))
			continue MainLoop
		}
		fmt.Println("update identified.")

		err = os.WriteFile(supervisorConfigPath, []byte(newSupervisorConfigContent), 0755)
		if err != nil {
			panic(fmt.Sprintf("panic in writing %s with %v", supervisorConfigPath, err))
		}

		var reloadConfigResult [][][]string
		err = supervisorXmlRpcClient.Call("supervisor.reloadConfig", nil, &reloadConfigResult)
		if err != nil {
			fmt.Printf("Error reloading supervisor config: %v\n", err)
			time.Sleep(time.Second * time.Duration(config.IntervalSec))
			continue MainLoop
		}
		added := reloadConfigResult[0][0]
		changed := reloadConfigResult[0][1]
		removed := reloadConfigResult[0][2]
		fmt.Printf("added %s changed %s remoded %s from supervisor\n", added, changed, removed)

		updateCmd := exec.Command("supervisorctl", "update")
		updateRes, err := updateCmd.Output()
		if err != nil {
			fmt.Printf("Error updating supervisor config: %v\n", err)
		}
		if updateRes != nil {
			fmt.Printf("supervisorctl updated result: %s\n", updateRes)
		}

		err = saveConfig(configPath, config)
		if err != nil {
			fmt.Printf("Error saving updated config: %v\n", err)
		}

		time.Sleep(time.Second * time.Duration(config.IntervalSec))
	}
}
