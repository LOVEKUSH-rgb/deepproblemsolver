"""tests/test_dependencies.py — Test dependency auto-appending."""

import os
from envfix.dependencies import (
    extract_package_name,
    update_requirements_txt,
    update_pyproject_toml,
)


def test_extract_package_name():
    assert extract_package_name("python -m pip install torch") == "torch"
    assert extract_package_name("pip install -U torch") == "torch"
    assert extract_package_name("pip install --upgrade pandas") == "pandas"
    assert extract_package_name("pip install -r requirements.txt") is None
    assert extract_package_name("npm install react") is None


def test_update_requirements_txt(tmp_path):
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy\n")
    
    update_requirements_txt(str(req_file), "torch")
    
    content = req_file.read_text()
    assert "numpy\ntorch\n" in content

    # Test avoids duplication
    update_requirements_txt(str(req_file), "torch")
    assert content.count("torch") == 1


def test_update_pyproject_toml_multiline(tmp_path):
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        "[project]\n"
        "dependencies = [\n"
        "    \"numpy\",\n"
        "]\n"
    )
    
    update_pyproject_toml(str(toml), "torch")
    
    content = toml.read_text()
    assert '"torch",' in content
    assert '"numpy"' in content
    assert content.count('"torch"') == 1
    
    # Avoid duplication
    update_pyproject_toml(str(toml), "torch")
    assert toml.read_text().count('"torch"') == 1


def test_update_pyproject_toml_single_line(tmp_path):
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        "[project]\n"
        "dependencies = [\"numpy\"]\n"
    )
    
    update_pyproject_toml(str(toml), "torch")
    
    content = toml.read_text()
    assert 'dependencies = ["torch", "numpy"]' in content


def test_update_pyproject_toml_empty_array(tmp_path):
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        "[project]\n"
        "dependencies = []\n"
    )
    
    update_pyproject_toml(str(toml), "torch")
    
    content = toml.read_text()
    assert 'dependencies = ["torch"]' in content
