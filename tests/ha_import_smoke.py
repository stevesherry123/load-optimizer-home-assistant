"""Run with the declared minimum Home Assistant installed, not with test stubs."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.load_optimizer.const import PLATFORMS

for module in ("config_flow", "diagnostics", *PLATFORMS):
    importlib.import_module(f"custom_components.load_optimizer.{module}")
print("All integration platform and config-flow imports passed")
