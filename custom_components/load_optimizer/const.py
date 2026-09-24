"""Constants for the Load Optimizer integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "load_optimizer"
MANUFACTURER = "Load Optimizer"
DEFAULT_NAME = "Load Optimizer"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

CONF_TARIFF_ENTITY = "tariff_entity"
CONF_TARIFF_TIMEZONE = "tariff_timezone"
CONF_TARIFF_PRICE_UNIT = "tariff_price_unit"
CONF_LOAD_TYPE = "load_type"
CONF_BATTERY_ENTITY = "battery_entity"
CONF_BATTERY_CAPACITY_ENTITY = "battery_capacity_entity"
CONF_TARGET_PERCENT_ENTITY = "target_percent_entity"
CONF_CONNECTION_STATUS_ENTITY = "connection_status_entity"
CONF_CHARGE_POWER_KW = "charge_power_kw"
CONF_CHARGER_EFFICIENCY = "charger_efficiency"
CONF_TARGET_PERCENT = "target_percent"
CONF_SLOT_MINUTES = "slot_minutes"
CONF_READY_BY = "ready_by"

LOAD_TYPE_EV = "ev_charging"
LOAD_TYPES = [LOAD_TYPE_EV]

PRICE_UNIT_PENCE = "p_per_kwh"
PRICE_UNIT_GBP = "gbp_per_kwh"
PRICE_UNITS = [PRICE_UNIT_PENCE, PRICE_UNIT_GBP]

DEFAULT_TARIFF_TIMEZONE = "Europe/London"
DEFAULT_TARIFF_PRICE_UNIT = PRICE_UNIT_PENCE
DEFAULT_TARGET_PERCENT = 100.0
DEFAULT_CHARGER_EFFICIENCY = 0.9
DEFAULT_SLOT_MINUTES = 30

PLATFORMS = ["sensor", "binary_sensor"]
