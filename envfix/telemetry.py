import os
import threading
from typing import Optional
from envfix.config import load_config
try:
    import httpx
except ImportError:
    import requests as httpx # fallback just in case, though google-genai pulled in requests/httpx

def send_telemetry(error_type: str, provider_used: str, was_cache_hit: bool, fix_applied: bool, fix_worked: Optional[bool], redacted_secrets_count: int = 0, fingerprint: str = ""):
    """
    Sends optional telemetry data to the team backend if configured.
    Fails silently on any error so as not to interrupt the user's workflow.
    """
    config = load_config()
    
    is_local = str(config.get("local_only", "")).lower() == "true" or config.get("local_only") is True
    if is_local:
        return
    
    
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
        "fix_worked": fix_worked,
        "installation_id": config.get("installation_id", ""),
        "redacted_secrets_count": redacted_secrets_count,
        "fingerprint": fingerprint
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
            with httpx.Client(timeout=1.0) as client:
                client.post(url, json=payload, headers=headers)
        except Exception:
            pass # Fail silently

    # Run in a background thread to not block the user, but daemon=False 
    # so the main thread waits up to 1 second for the HTTP call to finish
    threading.Thread(target=_post, daemon=False).start()

def send_doctor_telemetry(is_clean: bool, check_results: list):
    config = load_config()
    is_local = str(config.get("local_only", "")).lower() == "true" or config.get("local_only") is True
    if is_local:
        return
        
    api_key = os.environ.get("ENVFIX_TEAM_API_KEY", config.get("team_api_key"))
    backend_url = os.environ.get("ENVFIX_BACKEND_URL", config.get("backend_url"))
    
    if not api_key or not backend_url:
        return

    payload = {
        "installation_id": config.get("installation_id", ""),
        "is_clean": is_clean,
        "check_results": check_results
    }
    
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    url = f"{backend_url.rstrip('/')}/doctor_scans"

    def _post():
        try:
            import httpx
            with httpx.Client(timeout=1.0) as client:
                client.post(url, json=payload, headers=headers)
        except Exception:
            pass # Fail silently

    threading.Thread(target=_post, daemon=False).start()

