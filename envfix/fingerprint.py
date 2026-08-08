import re
import hashlib

def normalize_error(error_text: str) -> str:
    """
    Strips variable/environment-specific details before fingerprinting.
    """
    text = error_text

    # UUIDs
    text = re.sub(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b', '<uuid>', text)
    
    # Hex hashes (>= 32 chars like MD5, SHA)
    text = re.sub(r'\b[0-9a-fA-F]{32,}\b', '<hash>', text)
    
    # Hex memory addresses
    text = re.sub(r'\b0x[0-9a-fA-F]+\b', '<hex>', text)
    
    # Temp directories (match the full prefix so Windows absolute path doesn't partially match later)
    text = re.sub(r'(?:[a-zA-Z]:\\[^\n]*?\\AppData\\Local\\Temp\\|/tmp/|/var/folders/[^/]+/[^/]+/[^/]+/)[a-zA-Z0-9_.-]+', '<tempdir>', text, flags=re.IGNORECASE)
    
    # Timestamps (ISO 8601 or YYYY-MM-DD)
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?\b', '<timestamp>', text)
    
    # Version numbers (X.Y or X.Y.Z)
    text = re.sub(r'\b\d+\.\d+(?:\.\d+)?(?:[a-zA-Z0-9.-]+)?\b', '<version>', text)
    
    # IP Addresses
    text = re.sub(r'\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b', '<ip>', text)
    
    # Absolute Unix Paths (captures the last segment)
    text = re.sub(r'(?:/[a-zA-Z0-9_.-]+)+/([a-zA-Z0-9_.-]+)', r'<path>/\1', text)
    
    # Absolute Windows Paths (captures the last segment)
    text = re.sub(r'[a-zA-Z]:\\(?:[a-zA-Z0-9_.\s-]+\\)+([a-zA-Z0-9_.\s-]+)', r'<path>\\\1', text)
    
    # Line numbers (often change with minor code edits, causing cache misses)
    text = re.sub(r'\bline \d+\b', 'line <num>', text, flags=re.IGNORECASE)
    
    return text

def get_error_type(error_text: str) -> str:
    """Extract the core exception type from the error text."""
    error_lines = [line.strip() for line in error_text.splitlines() if line.strip()]
    if not error_lines:
        return "Unknown"
        
    last_line = error_lines[-1]
    if ":" in last_line:
        return last_line.split(":")[0].split(" ")[-1]
    else:
        return last_line[:50]

def generate_fingerprint(error_text: str, category: str) -> str:
    """Generate a stable, normalized SHA-256 fingerprint ID for an error."""
    normalized = normalize_error(error_text)
    error_type = get_error_type(error_text)
    
    combined = f"{normalized}:{error_type}:{category}"
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()[:16]
