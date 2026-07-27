import os
import threading
from typing import Optional
from envfix.config import load_config
try:
    import httpx
except ImportError:
    import requests as httpx # fallback just in case, though google-genai pulled in requests/httpx

def send_telemetry(error_type: str, provider_used: str, was_cache_hit: bool, fix_applied: bool, fix_worked: Optional[bool]):
    """
    Sends optional telemetry data to the team backend if configured.
    Fails silently on any error so as not to interrupt the user's workflow.
    """
    config = load_config()
    
    # Check env vars first, then config file
    api_key = os.environ.get("ENVFIX_TEAM_API_KEY", config.get("team_api_key"))
    backend_url = os.environ.get("ENVFIX_BACKEND_URL", config.get("backend_url"))
    
    if not api_key or not backend_url:
        return

    payload = {
        "error_type": error_type,
        "provider_used": provider_used,
        "was_cache_hit": was_cache_hit,
        "fix_applied": fix_applied,
        "fix_worked": fix_worked
    }
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    # Strip trailing slash from URL
    url = f"{backend_url.rstrip('/')}/events"

    def _post():
        try:
            import httpx
            with httpx.Client(timeout=3.0) as client:
                client.post(url, json=payload, headers=headers)
        except Exception:
            pass # Fail silently

    # Run in a background thread to not block the user
    threading.Thread(target=_post, daemon=True).start()
