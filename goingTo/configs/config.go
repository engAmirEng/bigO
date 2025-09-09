package configs

type Config struct {
	Xray struct {
		APIPort    int    `toml:"api_port"`
		APIHost    string `toml:"api_host"`
		MetricsUrl string `toml:"metrics_url"`
		//Config  xray.Config
		Usage *struct {
			Interval int  `toml:"interval"`
			Reset    bool `toml:"reset"`
		} `toml:"usage"`
		Metrics *struct {
			Interval int `toml:"interval"`
		} `toml:"metric"`
	} `toml:"xray"`
}
