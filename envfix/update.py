import importlib.metadata
import threading
import time
from datetime import datetime, timezone
import requests
from envfix.config import load_config, save_config
from rich.console import Console

console = Console(stderr=True)

_update_message = None
_update_thread = None

def _fetch_update_info():
    global _update_message
    try:
        config = load_config()
        last_check = config.get("last_update_check")
        now = time.time()
        
        if last_check and now - last_check < 86400:
            return  # Checked within last 24 hours
            
        current_version = importlib.metadata.version("envfix")
        
        response = requests.get("https://pypi.org/pypi/envfix/json", timeout=2)
        if response.status_code == 200:
            data = response.json()
            latest_version = data["info"]["version"]
            
            # Simple version comparison (assuming standard semver-ish versions)
            def parse_version(v):
                return tuple(int(x) if x.isdigit() else x for x in v.split('.'))
                
            if parse_version(latest_version) > parse_version(current_version):
                _update_message = f"\n[dim cyan][i] A new version of envfix is available ({current_version} -> {latest_version}). Run 'pip install --upgrade envfix' to get the latest features.[/dim cyan]"
                
            # Update cache timestamp
            config["last_update_check"] = now
            save_config(config)
    except Exception:
        pass # Fail silently on network errors or parsing errors

def start_update_check():
    global _update_thread
    _update_thread = threading.Thread(target=_fetch_update_info, daemon=True)
    _update_thread.start()

def print_update_message_if_available():
    if _update_thread:
        # We don't want to block the exit indefinitely. Wait up to 0.0s for the update check.
        _update_thread.join(timeout=0.0)
    if _update_message:
        console.print(_update_message)
