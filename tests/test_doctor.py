import pytest
from unittest import mock
from envfix.doctor import check_python, check_node, check_cuda, check_torch_cuda_compat, CheckResult

def test_check_python_installed():
    with mock.patch("envfix.doctor._run_cmd", return_value="Python 3.12.1"):
        res = check_python()
        assert res.ok is True
        assert res.version == "3.12.1"

def test_check_python_missing():
    with mock.patch("envfix.doctor._run_cmd", return_value=None):
        res = check_python()
        assert res.ok is False
        assert "not installed" in res.warning

def test_check_node_installed():
    with mock.patch("envfix.doctor._run_cmd", return_value="v20.11.0"):
        res = check_node()
        assert res.ok is True
        assert res.version == "20.11.0"

def test_check_cuda_nvcc():
    out = "nvcc: NVIDIA (R) Cuda compiler driver\nCuda compilation tools, release 12.6, V12.6.20\n"
    with mock.patch("envfix.doctor._run_cmd", side_effect=lambda cmd: out if "nvcc" in cmd else None):
        res = check_cuda()
        assert res.ok is True
        assert res.version == "12.6"

def test_check_cuda_nvidia_smi():
    out = "NVIDIA-SMI 560.81       Driver Version: 560.81       CUDA Version: 12.6"
    with mock.patch("envfix.doctor._run_cmd", side_effect=lambda cmd: out if "nvidia-smi" in cmd else None):
        res = check_cuda()
        assert res.ok is True
        assert res.version == "12.6"

def test_check_torch_cuda_compat_match():
    # 2.5.0 requires 11.8 or 12.4
    with mock.patch("envfix.doctor._run_cmd", return_value="2.5.0"):
        res = check_torch_cuda_compat("12.4")
        assert res.ok is True
        assert res.warning is None

def test_check_torch_cuda_compat_mismatch():
    # 2.5.0 requires 11.8 or 12.4, system is 12.6
    with mock.patch("envfix.doctor._run_cmd", return_value="2.5.0"):
        res = check_torch_cuda_compat("12.6")
        assert res.ok is False
        assert res.warning == "CUDA 12.6 detected, but installed PyTorch 2.5.0 requires CUDA 11.8 or 12.4"
        assert res.details == "Requires 11.8 or 12.4"

def test_check_torch_cuda_compat_no_torch():
    with mock.patch("envfix.doctor._run_cmd", return_value=None):
        res = check_torch_cuda_compat("12.6")
        assert res.ok is True
        assert res.details == "Not installed"

def test_check_torch_cuda_compat_unknown_version():
    with mock.patch("envfix.doctor._run_cmd", return_value="1.9.0"):
        res = check_torch_cuda_compat("10.2")
        # Not in our limited DB, so we assume OK
        assert res.ok is True
        assert res.warning is None
