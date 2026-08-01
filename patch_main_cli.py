import sys

with open("envfix/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Imports
content = content.replace(
    "from envfix.redact import redact_secrets",
    "from envfix.redact import redact_secrets, redact_secrets_with_count"
)

# 2. In run_cmd, we capture the command error and redact it.
content = content.replace(
    """    error_text = redact_secrets(stderr.strip() or stdout.strip() or "(no output captured)")""",
    """    error_text, secrets_count1 = redact_secrets_with_count(stderr.strip() or stdout.strip() or "(no output captured)")"""
)
content = content.replace(
    """        original_command=redact_secrets(cmd),""",
    """        original_command=redact_secrets(cmd),
        redacted_secrets_count=locals().get('secrets_count1', 0) + locals().get('secrets_count2', 0),"""
)
content = content.replace(
    """    error_text = redact_secrets(f.read().strip())""",
    """    error_text, secrets_count1 = redact_secrets_with_count(f.read().strip())"""
)

with open("envfix/main.py", "w", encoding="utf-8") as f:
    f.write(content)
