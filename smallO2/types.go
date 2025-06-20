package main

import "time"

type Config struct {
	SyncURL                  string  `toml:"sync_url" json:"sync_url"`
	APIKey                   string  `toml:"api_key" json:"api_key"`
	IntervalSec              int     `toml:"interval_sec" json:"interval_sec"`
	WorkingDir               string  `toml:"working_dir" json:"working_dir"`
	IsDev                    bool    `toml:"is_dev" json:"is_dev"`
	SentryDsn                *string `toml:"sentry_dsn" json:"sentry_dsn"`
	FullControlSupervisord   bool    `toml:"full_control_supervisord" json:"full_control_supervisord"`
	SupervisorBaseConfigPath string  `toml:"supervisor_base_config_path" json:"supervisor_base_config_path"`
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
	Name          string `xmlrpc:"name" json:"name"`
	Group         string `xmlrpc:"group" json:"group"`
	Description   string `xmlrpc:"description" json:"description"`
	Start         int    `xmlrpc:"start" json:"start"`
	Stop          int    `xmlrpc:"stop" json:"stop"`
	Now           int    `xmlrpc:"now" json:"now"`
	State         int    `xmlrpc:"state" json:"state"`
	StateName     string `xmlrpc:"statename" json:"statename"`
	SpawnErr      string `xmlrpc:"spawnerr" json:"spawnerr"`
	ExitStatus    int    `xmlrpc:"exitstatus" json:"exitstatus"`
	StdoutLogfile string `xmlrpc:"stdout_logfile" json:"stdout_logfile"`
	StderrLogfile string `xmlrpc:"stderr_logfile" json:"stderr_logfile"`
	PID           int    `xmlrpc:"pid" json:"pid"`
}
type SupervisorProcessTailLogSerializerSchema struct {
	Bytes    string `json:"bytes"`
	Offset   int64  `json:"offset"`
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
