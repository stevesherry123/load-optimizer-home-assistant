#!/usr/bin/with-contenv bashio
set -e

export LOAD_OPTIMIZER_LOG_LEVEL="$(bashio::config 'log_level')"
export LOAD_OPTIMIZER_SCAN_INTERVAL="$(bashio::config 'scan_interval')"
export LOAD_OPTIMIZER_INSTANCE_1_NAME="$(bashio::config 'instance_1_name')"
export LOAD_OPTIMIZER_INSTANCE_1_POWER_SENSOR="$(bashio::config 'instance_1_power_sensor')"
export LOAD_OPTIMIZER_INSTANCE_1_ENERGY_SENSOR="$(bashio::config 'instance_1_energy_sensor')"
export LOAD_OPTIMIZER_INSTANCE_1_PROGRAM_SENSOR="$(bashio::config 'instance_1_program_sensor')"
export LOAD_OPTIMIZER_INSTANCE_1_STATE_SENSOR="$(bashio::config 'instance_1_state_sensor')"
export LOAD_OPTIMIZER_INSTANCE_1_ACTIVE_POWER_THRESHOLD="$(bashio::config 'instance_1_active_power_threshold')"
export LOAD_OPTIMIZER_INSTANCE_1_FINISH_DELAY="$(bashio::config 'instance_1_finish_delay')"

bashio::log.info "Starting Load Optimizer"
exec python3 -u /app/main.py
