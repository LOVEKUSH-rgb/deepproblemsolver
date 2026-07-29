import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class CheckResult:
    name: str
    ok: bool
    version: Optional[str]
    warning: Optional[str]
    details: Optional[str] = None

def _run_cmd(cmd: List[str]) -> Optional[str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None

def check_python() -> CheckResult:
    out = _run_cmd(["python", "--version"])
    if out:
        version = out.replace("Python ", "").strip()
        return CheckResult(name="Python", ok=True, version=version, warning=None)
    return CheckResult(name="Python", ok=False, version=None, warning="Python is not installed or not on PATH.")

def check_node() -> CheckResult:
    out = _run_cmd(["node", "--version"])
    if out:
        version = out.strip().lstrip("v")
        return CheckResult(name="Node.js", ok=True, version=version, warning=None)
    return CheckResult(name="Node.js", ok=True, version=None, warning=None, details="Not installed")

def check_cuda() -> CheckResult:
    out = _run_cmd(["nvcc", "--version"])
    if out:
        match = re.search(r"release (\d+\.\d+)", out)
        if match:
            return CheckResult(name="CUDA", ok=True, version=match.group(1), warning=None)
    
    # Try nvidia-smi if nvcc fails
    out = _run_cmd(["nvidia-smi"])
    if out:
        match = re.search(r"CUDA Version:\s*(\d+\.\d+)", out)
        if match:
            return CheckResult(name="CUDA", ok=True, version=match.group(1), warning=None)
            
    return CheckResult(name="CUDA", ok=True, version=None, warning=None, details="No GPU/CUDA detected")

def check_torch_cuda_compat(system_cuda_version: Optional[str]) -> CheckResult:
    if not system_cuda_version:
        return CheckResult(name="PyTorch-CUDA Compat", ok=True, version=None, warning=None)

    # Check installed torch version
    out = _run_cmd(["python", "-c", "import torch; print(torch.__version__)"])
    if not out:
        return CheckResult(name="PyTorch", ok=True, version=None, warning=None, details="Not installed")
        
    torch_version_full = out.strip()
    # Extract just the X.Y.Z part (ignoring +cu121 etc)
    match = re.match(r"^(\d+\.\d+\.\d+)", torch_version_full)
    if not match:
        return CheckResult(name="PyTorch", ok=True, version=torch_version_full, warning=None)
        
    torch_version = match.group(1)
    
    # Load knowledge base
    kb_path = os.path.join(os.path.dirname(__file__), "known_incompatibilities.json")
    if not os.path.exists(kb_path):
        return CheckResult(name="PyTorch-CUDA Compat", ok=True, version=torch_version, warning=None)
        
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            kb = json.load(f)
    except Exception:
        return CheckResult(name="PyTorch-CUDA Compat", ok=True, version=torch_version, warning=None)
        
    matrix = kb.get("torch_cuda_matrix", [])
    required_cuda = None
    for entry in matrix:
        if entry.get("torch_version") == torch_version:
            required_cuda = entry.get("cuda_required")
            break
            
    if not required_cuda:
        # Not in our limited database, assume OK
        return CheckResult(name="PyTorch", ok=True, version=torch_version, warning=None)
        
    # Simple heuristic: if the system_cuda_version is not explicitly mentioned in required_cuda, warn
    # e.g., system is "12.6", required_cuda is "11.8 or 12.4"
    if system_cuda_version not in required_cuda:
        warning = f"CUDA {system_cuda_version} detected, but installed PyTorch {torch_version} requires CUDA {required_cuda}"
        return CheckResult(name="PyTorch", ok=False, version=torch_version, warning=warning, details=f"Requires {required_cuda}")
        
    return CheckResult(name="PyTorch", ok=True, version=torch_version, warning=None)

def check_docker() -> CheckResult:
    out = _run_cmd(["docker", "--version"])
    if not out:
        return CheckResult(name="Docker", ok=True, version=None, warning=None, details="Not installed")
    
    version = out.replace("Docker version ", "").split(",")[0].strip()
    
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return CheckResult(name="Docker", ok=False, version=version, warning="Docker is installed but the daemon is not running.", details="Daemon inactive")
    except Exception:
        return CheckResult(name="Docker", ok=False, version=version, warning="Docker is installed but the daemon is not running or unreachable.", details="Daemon inactive")
        
    return CheckResult(name="Docker", ok=True, version=version, warning=None, details="Daemon running")


def check_conda() -> CheckResult:
    out = _run_cmd(["conda", "--version"])
    if not out:
        return CheckResult(name="Conda", ok=True, version=None, warning=None, details="Not installed")
        
    version = out.replace("conda ", "").strip()
    active_env = os.environ.get("CONDA_DEFAULT_ENV", "base")
    
    env_yml_path = os.path.join(os.getcwd(), "environment.yml")
    if os.path.exists(env_yml_path):
        try:
            with open(env_yml_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("name:"):
                        expected_env = line.split(":", 1)[1].strip()
                        # Unquote if necessary
                        if expected_env.startswith('"') and expected_env.endswith('"'):
                            expected_env = expected_env[1:-1]
                        elif expected_env.startswith("'") and expected_env.endswith("'"):
                            expected_env = expected_env[1:-1]
                            
                        if expected_env and expected_env != active_env:
                            warning = f"Active conda environment '{active_env}' does not match expected '{expected_env}' from environment.yml"
                            return CheckResult(name="Conda", ok=False, version=version, warning=warning, details=f"Expected: {expected_env}")
                        break
        except Exception:
            pass
            
    return CheckResult(name="Conda", ok=True, version=version, warning=None, details=f"Active env: {active_env}")


def check_path() -> CheckResult:
    python_path = _run_cmd(["where", "python"])
    pip_path = _run_cmd(["where", "pip"])
    
    if python_path and pip_path:
        python_primary = python_path.splitlines()[0].strip().lower()
        pip_primary = pip_path.splitlines()[0].strip().lower()
        
        python_dir = os.path.dirname(python_primary)
        pip_dir = os.path.dirname(pip_primary)
        
        def get_base(p: str) -> str:
            return p.replace("\\scripts", "").replace("\\bin", "")
            
        if get_base(python_dir) != get_base(pip_dir):
            warning = f"Python and pip resolve to different environments. Python: {python_primary}, Pip: {pip_primary}"
            return CheckResult(name="PATH", ok=False, version=None, warning=warning, details="Inconsistent paths")
            
    return CheckResult(name="PATH", ok=True, version=None, warning=None)


def run_all_checks(
    run_python: bool = True,
    run_node: bool = True,
    run_gpu: bool = True,
    run_docker: bool = True,
    run_conda: bool = True,
    run_path: bool = True,
) -> List[CheckResult]:
    results = []
    
    if run_python:
        results.append(check_python())
    if run_node:
        results.append(check_node())
    if run_gpu:
        cuda_result = check_cuda()
        results.append(cuda_result)
        if cuda_result.version:
            results.append(check_torch_cuda_compat(cuda_result.version))
    if run_docker:
        results.append(check_docker())
    if run_conda:
        results.append(check_conda())
    if run_path:
        results.append(check_path())
        
    return results
