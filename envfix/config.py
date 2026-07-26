import os
import sys
from pathlib import Path
from typing import Dict, Any

import typer
import yaml
from rich.console import Console

console = Console()

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
            global_config = tomllib.load(f)
    except Exception:
        global_config = {}

    project_config = load_project_config()
    
    # Merge project config over global config
    for k, v in project_config.items():
        global_config[k] = v
        
    return global_config

def load_project_config() -> Dict[str, Any]:
    """Load the project-specific YAML configuration file."""
    yaml_file = Path.cwd() / ".envfix.yaml"
    if not yaml_file.exists():
        return {}
        
    try:
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        console.print(f"\n[bold red]✗ Failed to parse .envfix.yaml:[/bold red]\n{e}")
        raise typer.Exit(code=1)
    except OSError:
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
