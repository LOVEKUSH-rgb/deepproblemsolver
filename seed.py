import requests
from envfix.signature import generate_signature

error = """
Traceback (most recent call last):
  File "C:\\Users\\lovek\\.gemini\\antigravity-ide\\scratch\\envfix\\dummy_fail.py", line 5, in <module>
    result = math.fabs(-0) / 0
             ~~~~~~~~~~~~~~~~~~^~~
ZeroDivisionError: float division by zero
"""

sig = generate_signature(error, "python")
print("Signature:", sig)

url = "http://localhost:8000/community/report"
payload = {
    "signature": sig,
    "category": "python",
    "fix_command": "python -c \"print('Community Fix Applied')\"",
    "worked": True
}

for i in range(12):
    res = requests.post(url, json=payload)
    print(i, res.status_code, res.text)
