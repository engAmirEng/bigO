package configs

import "bigO/goingTo/xray"

type Config struct {
	Xray struct {
		APIPort int    `toml:"api_port"`
		APIHost string `toml:"api_host"`
		Config  xray.Config
	} `toml:"xray"`

	Usage struct {
		Interval int `toml:"interval"`
	} `toml:"usage"`

	Logging struct {
		Level string `toml:"level"`
		File  string `toml:"file"`
	} `toml:"logging"`
}
