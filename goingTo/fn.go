package main

import (
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"os"
)

func configureLogger() *zap.Logger {
	consoleSyncer := zapcore.AddSync(os.Stderr)

	encoderCfg := zap.NewProductionEncoderConfig()
	encoderCfg.TimeKey = "timestamp"
	encoderCfg.EncodeTime = zapcore.ISO8601TimeEncoder

	core := zapcore.NewCore(zapcore.NewJSONEncoder(encoderCfg), consoleSyncer, zap.DebugLevel)

	logger := zap.New(core)
	return logger
}

func configureOutput() *zap.Logger {
	consoleSyncer := zapcore.AddSync(os.Stdout)

	encoderCfg := zap.NewProductionEncoderConfig()
	encoderCfg.TimeKey = "timestamp"
	encoderCfg.EncodeTime = zapcore.ISO8601TimeEncoder

	core := zapcore.NewCore(zapcore.NewJSONEncoder(encoderCfg), consoleSyncer, zap.DebugLevel)

	logger := zap.New(core)
	return logger
}
