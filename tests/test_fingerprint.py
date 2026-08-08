import pytest
from envfix.fingerprint import normalize_error, generate_fingerprint, get_error_type

def test_normalize_error_uuids():
    text = "Error in volume 123e4567-e89b-12d3-a456-426614174000"
    assert normalize_error(text) == "Error in volume <uuid>"

def test_normalize_error_hex_hashes():
    text = "Commit a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2 failed"
    assert normalize_error(text) == "Commit <hash> failed"

def test_normalize_error_memory_addresses():
    text = "Object at 0x7f8b9c0d1e2f failed"
    assert normalize_error(text) == "Object at <hex> failed"

def test_normalize_error_versions():
    text = "Required package==2.5.1 not found"
    assert normalize_error(text) == "Required package==<version> not found"

def test_normalize_error_temp_directories():
    text1 = "File /tmp/test-xyz123/module.py not found"
    assert normalize_error(text1) == "File <tempdir>/module.py not found"
    
    text2 = r"File C:\Users\lovek\AppData\Local\Temp\pytest-12\module.py not found"
    assert normalize_error(text2) == r"File <tempdir>\module.py not found"

def test_normalize_error_timestamps():
    text = "Log from 2026-08-08T23:22:24Z crashed"
    assert normalize_error(text) == "Log from <timestamp> crashed"

def test_normalize_error_absolute_paths():
    text_unix = "Traceback at /home/user/workspace/project/main.py"
    assert normalize_error(text_unix) == "Traceback at <path>/main.py"
    
    text_win = r"Traceback at C:\Users\lovek\project\main.py"
    assert normalize_error(text_win) == r"Traceback at <path>\main.py"

def test_normalize_error_line_numbers():
    text = "Error in line 42"
    assert normalize_error(text) == "Error in line <num>"

def test_fingerprint_uniqueness_and_consistency():
    # Two identical errors with different paths, versions, and line numbers
    error_a = """Traceback (most recent call last):
  File "C:\\Users\\lovek\\project_a\\main.py", line 42, in <module>
    import missing_pkg
ModuleNotFoundError: No module named 'missing_pkg' (version 1.0.0)"""
    
    error_b = """Traceback (most recent call last):
  File "C:\\Users\\someone\\other_project\\main.py", line 87, in <module>
    import missing_pkg
ModuleNotFoundError: No module named 'missing_pkg' (version 2.1.3)"""
    
    # Should produce same fingerprint
    fp_a = generate_fingerprint(error_a, "python")
    fp_b = generate_fingerprint(error_b, "python")
    assert fp_a == fp_b

    # A genuinely different error
    error_c = """Traceback (most recent call last):
  File "C:\\Users\\lovek\\project_a\\main.py", line 42, in <module>
    import something_else
ModuleNotFoundError: No module named 'something_else'"""
    
    fp_c = generate_fingerprint(error_c, "python")
    assert fp_a != fp_c

def test_get_error_type():
    error_a = """Traceback (most recent call last):
  File "main.py", line 42, in <module>
    import missing_pkg
ModuleNotFoundError: No module named 'missing_pkg'"""
    assert get_error_type(error_a) == "ModuleNotFoundError"
    
    error_b = "npm ERR! missing script: build"
    assert get_error_type(error_b) == "script" # based on existing logic split(" ")[-1]
