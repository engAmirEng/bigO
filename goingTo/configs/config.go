package configs

type Config struct {
	Xray struct {
		APIPort int    `toml:"api_port"`
		APIHost string `toml:"api_host"`
		//Config  xray.Config
		Usage struct {
			Interval int  `toml:"interval"`
			Reset    bool `toml:"reset"`
		} `toml:"usage"`
	} `toml:"xray"`
}
