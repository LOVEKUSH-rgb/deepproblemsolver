import os
import sys
from pathlib import Path
from typing import Dict, Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w

CONFIG_DIR = Path.home() / ".envfix"
CONFIG_FILE = CONFIG_DIR / "config.toml"

def load_config() -> Dict[str, Any]:
    """Load the persistent TOML configuration file."""
    if not CONFIG_FILE.exists():
        return {}
    
    try:
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}

def save_config(data: Dict[str, Any]) -> None:
    """Save the configuration dict to TOML."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(data, f)

def reset_config() -> None:
    """Delete the configuration file."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
