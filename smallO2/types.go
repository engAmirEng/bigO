package main

import "time"

type UrlSpec struct {
	URL      string `toml:"url" json:"url"`
	ProxyUrl string `toml:"proxy_url" json:"proxy_url"`
	Weight   int    `toml:"weight" json:"weight"`
}
type ProcLogCollection struct {
	Name   string `toml:"name" json:"name"`
	Stderr *bool  `toml:"stderr" json:"stderr"`
	Stdout *bool  `toml:"stdout" json:"stdout"`
}
type Config struct {
	SyncURL      string    `toml:"sync_url" json:"sync_url"` // Deprecated
	SyncURLSpecs []UrlSpec `toml:"sync_urls" json:"sync_urls"`
	//ProxyUrl                 string    `toml:"proxy_url" json:"proxy_url"`
	APIKey                   string               `toml:"api_key" json:"api_key"`
	IntervalSec              int                  `toml:"interval_sec" json:"interval_sec"`
	WorkingDir               string               `toml:"working_dir" json:"working_dir"`
	IsDev                    bool                 `toml:"is_dev" json:"is_dev"`
	SentryDsn                *string              `toml:"sentry_dsn" json:"sentry_dsn"`
	FullControlSupervisord   bool                 `toml:"full_control_supervisord" json:"full_control_supervisord"`
	SupervisorBaseConfigPath string               `toml:"supervisor_base_config_path" json:"supervisor_base_config_path"`
	SafeStatsSize            int                  `toml:"safe_stats_size" json:"safe_stats_size"`
	EachCollectionSize       int                  `toml:"each_collection_size" json:"each_collection_size"`
	LogsCollection           *[]ProcLogCollection `toml:"logs_collection" json:"logs_collection"`
}

type FileSchema struct {
	DestPath   string  `json:"dest_path"`
	Content    *string `json:"content"`
	URL        *string `json:"url"`
	Permission int     `json:"permission"`
	Hash       *string `json:"hash"`
}

type SupervisorConfig struct {
	ConfigContent string `json:"config_content"`
}

type RuntimeSchema struct {
	NodeID   string `json:"node_id"`
	NodeName string `json:"node_name"`
}

// APIResponse represents the response from the server
type APIResponse struct {
	SupervisorConfig SupervisorConfig `json:"supervisor_config"`
	Files            []FileSchema     `json:"files"`
	Config           Config           `json:"config"`
	Runtime          RuntimeSchema    `json:"runtime"`
}
type SupervisorProcessInfoSchema struct {
	Name          string `xmlrpc:"Name" json:"name"`
	Group         string `xmlrpc:"Group" json:"group"`
	Description   string `xmlrpc:"Description" json:"description"`
	Start         int    `xmlrpc:"Start" json:"start"`
	Stop          int    `xmlrpc:"Stop" json:"stop"`
	Now           int    `xmlrpc:"Now" json:"now"`
	State         int    `xmlrpc:"State" json:"state"`
	StateName     string `xmlrpc:"Statename" json:"statename"`
	SpawnErr      string `xmlrpc:"Spawnerr" json:"spawnerr"`
	ExitStatus    int    `xmlrpc:"Exitstatus" json:"exitstatus"`
	Logfile       string `xmlrpc:"Logfile" json:"logfile"` //deprecated, just for alexejk-xmlrpc
	StdoutLogfile string `xmlrpc:"Stdout_logfile" json:"stdout_logfile"`
	StderrLogfile string `xmlrpc:"Stderr_logfile" json:"stderr_logfile"`
	PID           int    `xmlrpc:"Pid" json:"pid"`
}
type SupervisorProcessTailLogSerializerSchema struct {
	Bytes    string `json:"bytes"`
	Offset   int    `json:"offset"`
	Overflow bool   `json:"overflow"`
}
type ConfigStateSchema struct {
	Time                  time.Time                                `json:"time"`
	SupervisorProcessInfo SupervisorProcessInfoSchema              `json:"supervisorprocessinfo"`
	Stdout                SupervisorProcessTailLogSerializerSchema `json:"stdout"`
	Stderr                SupervisorProcessTailLogSerializerSchema `json:"stderr"`
}
type MetricSchema struct {
	IPA string `json:"ip_a"`
}
type APIRequest struct {
	Metrics       MetricSchema                             `json:"metrics"`
	ConfigsStates []ConfigStateSchema                      `json:"configs_states"`
	SelfLogs      SupervisorProcessTailLogSerializerSchema `json:"self_logs"`
	Config        Config                                   `json:"config"`
}

type backFileInfo struct {
	path string
	size int
	time time.Time
}
