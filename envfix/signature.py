import hashlib
import re
from envfix.redact import redact_secrets

def generate_signature(error_text: str, category: str) -> str:
    """
    Generates a highly anonymized, deterministic hash of an error's shape.
    Strips out secrets, file paths, variable names, line numbers, and hex strings.
    """
    if not error_text:
        return ""
        
    text = redact_secrets(error_text)
    
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
        
    core_error = lines[-1]
    
    # If the last line is very short or uninformative, take a bit more context
    if len(core_error) < 10 or "error:" == core_error.lower():
        core_error = " ".join(lines[-min(3, len(lines)):])
        
    # Strip file paths (Windows and Unix)
    core_error = re.sub(r'(?:[a-zA-Z]:\\|/|\./)[^\s:\[\]]+', '', core_error)
    
    # Strip hex strings/hashes
    core_error = re.sub(r'\b(?:0x)[a-fA-F0-9]+\b|\b[a-fA-F0-9]{8,}\b', '', core_error)
    
    # Strip line numbers
    core_error = re.sub(r'\bline \d+\b', '', core_error, flags=re.IGNORECASE)
    core_error = re.sub(r':\d+', '', core_error)
    
    # Strip quoted strings (often variable names, module names, or user input)
    core_error = re.sub(r'["\'].*?["\']', '', core_error)
    
    # Strip standalone numbers
    core_error = re.sub(r'\b\d+\b', '', core_error)
    
    # Normalize whitespace and case
    core_error = re.sub(r'\W+', ' ', core_error).strip().lower()
    
    # Create the final hash
    raw = f"{category}:{core_error}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
