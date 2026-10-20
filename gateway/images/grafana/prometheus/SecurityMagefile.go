//go:build mage

package main

import (
	"encoding/json"
	build "github.com/grafana/grafana-plugin-sdk-go/build"
)

func SecurityLinux() error {
	if err := build.SetBeforeBuildCallback(func(cfg build.Config) (build.Config, error) {
		info, err := json.Marshal(map[string]any{"time": int64(1792490400000), "pluginID": "prometheus", "version": "13.2.3+ambicrafted.20261020"})
		if err != nil {
			return cfg, err
		}
		cfg.CustomVars = map[string]string{"github.com/grafana/grafana-plugin-sdk-go/build/buildinfo.buildInfoJSON": string(info)}
		if cfg.Env == nil {
			cfg.Env = map[string]string{}
		}
		cfg.Env["GOFLAGS"] = "-mod=readonly -trimpath -buildvcs=false -p=4"
		cfg.Env["GOTOOLCHAIN"] = "local"
		cfg.Env["GOTELEMETRY"] = "off"
		return cfg, nil
	}); err != nil {
		return err
	}
	return build.Build{}.Linux()
}
