import pytest
from envfix.signature import generate_signature

def test_signature_strips_paths():
    error1 = """
Traceback (most recent call last):
  File "C:\\Users\\lovek\\main.py", line 12, in <module>
    print(1 / 0)
ZeroDivisionError: division by zero
"""
    error2 = """
Traceback (most recent call last):
  File "/home/user/app/main.py", line 99, in <module>
    print(1 / 0)
ZeroDivisionError: division by zero
"""
    sig1 = generate_signature(error1, "python")
    sig2 = generate_signature(error2, "python")
    assert sig1 == sig2
    assert sig1 != ""

def test_signature_strips_variables():
    error1 = "KeyError: 'api_key_1234'"
    error2 = "KeyError: 'secret_token_5678'"
    
    sig1 = generate_signature(error1, "python")
    sig2 = generate_signature(error2, "python")
    assert sig1 == sig2

def test_signature_strips_hex():
    error1 = "MemoryError: unable to allocate 0x7fa8b9c at 0xdeadbeef"
    error2 = "MemoryError: unable to allocate 0x1234567 at 0x00000000"
    
    sig1 = generate_signature(error1, "general")
    sig2 = generate_signature(error2, "general")
    assert sig1 == sig2

def test_signature_strips_line_numbers():
    error1 = "Error at line 123"
    error2 = "Error at line 456"
    
    sig1 = generate_signature(error1, "docker")
    sig2 = generate_signature(error2, "docker")
    assert sig1 == sig2
