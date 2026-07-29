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

def run_all_checks() -> List[CheckResult]:
    results = []
    results.append(check_python())
    results.append(check_node())
    cuda_result = check_cuda()
    results.append(cuda_result)
    
    if cuda_result.version:
        results.append(check_torch_cuda_compat(cuda_result.version))
        
    return results
