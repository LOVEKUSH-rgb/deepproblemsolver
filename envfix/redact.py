import re

def redact_secrets(text: str) -> str:
    """
    Scans a string and replaces detected secrets with [REDACTED:...] placeholders.
    This is best-effort pattern matching to prevent accidental leakage.
    """
    if not text:
        return text

    # 1. AWS Access Keys
    text = re.sub(r'AKIA[0-9A-Z]{16}', '[REDACTED:AWS_KEY]', text)

    # 2. JWT Tokens (eyJ...)
    # JWTs are 3 parts separated by dots. First part is usually eyJ.
    text = re.sub(
        r'eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*',
        '[REDACTED:JWT]',
        text
    )

    # 3. Database URLs
    # postgres://user:pass@host:port/db -> postgres://[REDACTED_CREDENTIALS]@host:port/db
    # mysql://, mongodb://, mongodb+srv://
    # We use a callable to replace only the user:pass group while preserving the rest.
    def db_replacer(match: re.Match) -> str:
        protocol = match.group(1)
        host_and_rest = match.group(4)
        return f"{protocol}://[REDACTED_CREDENTIALS]@{host_and_rest}"
    
    text = re.sub(
        r'(?i)(postgres|postgresql|mysql|mongodb(?:\+srv)?|sqlite)://([^:/?#\s]+):([^/?#\s]+)@(\S+)',
        db_replacer,
        text
    )

    # 4. Private Keys
    text = re.sub(
        r'-----BEGIN.*?PRIVATE KEY-----.*?-----END.*?PRIVATE KEY-----',
        '[REDACTED:PRIVATE_KEY]',
        text,
        flags=re.DOTALL
    )

    # 5. Generic high-entropy strings
    # Looks for variable names like API_KEY, SECRET, TOKEN, PASSWORD, CREDENTIAL
    # followed by = or : and a string > 20 chars long.
    # We will match the variable name, the separator, optional quotes, and then the long string.
    def generic_replacer(match: re.Match) -> str:
        var_name = match.group(1)
        separator = match.group(2)
        quote = match.group(3) or ""
        # The secret itself is match.group(4)
        return f"{var_name}{separator}{quote}[REDACTED:SECRET]{quote}"
    
    text = re.sub(
        r'(?i)\b(api_key|secret|token|password|credential)\b(\s*[:=]\s*)([\'"]?)([A-Za-z0-9-_]{20,})\3',
        generic_replacer,
        text
    )

    return text
