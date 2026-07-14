#!/usr/bin/with-contenv bashio
set -e

export LOAD_OPTIMIZER_LOG_LEVEL="$(bashio::config 'log_level')"
export LOAD_OPTIMIZER_SCAN_INTERVAL="$(bashio::config 'scan_interval')"

bashio::log.info "Starting Load Optimizer"
exec python3 -u /app/main.py
