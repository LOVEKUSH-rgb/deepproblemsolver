import pytest
from unittest import mock
from envfix.doctor import check_python, check_node, check_cuda, check_torch_cuda_compat, check_docker, check_conda, check_path, CheckResult

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

def test_check_docker_missing():
    with mock.patch("envfix.doctor._run_cmd", return_value=None):
        res = check_docker()
        assert res.ok is True
        assert res.details == "Not installed"

def test_check_docker_installed_not_running():
    with mock.patch("envfix.doctor._run_cmd", return_value="Docker version 24.0.5, build ced0996"):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            res = check_docker()
            assert res.ok is False
            assert res.version == "24.0.5"
            assert "daemon is not running" in res.warning

def test_check_docker_installed_running():
    with mock.patch("envfix.doctor._run_cmd", return_value="Docker version 24.0.5, build ced0996"):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            res = check_docker()
            assert res.ok is True
            assert res.version == "24.0.5"

def test_check_conda_missing():
    with mock.patch("envfix.doctor._run_cmd", return_value=None):
        res = check_conda()
        assert res.ok is True
        assert res.details == "Not installed"

def test_check_conda_matching():
    with mock.patch("envfix.doctor._run_cmd", return_value="conda 23.3.1"):
        with mock.patch("os.environ.get", return_value="myenv"):
            with mock.patch("os.path.exists", return_value=True):
                m_open = mock.mock_open(read_data="name: myenv\ndependencies:\n  - python=3.10")
                with mock.patch("builtins.open", m_open):
                    res = check_conda()
                    assert res.ok is True
                    assert res.version == "23.3.1"

def test_check_conda_mismatch():
    with mock.patch("envfix.doctor._run_cmd", return_value="conda 23.3.1"):
        with mock.patch("os.environ.get", return_value="base"):
            with mock.patch("os.path.exists", return_value=True):
                m_open = mock.mock_open(read_data="name: myenv\ndependencies:\n  - python=3.10")
                with mock.patch("builtins.open", m_open):
                    res = check_conda()
                    assert res.ok is False
                    assert "does not match expected 'myenv'" in res.warning

def test_check_path_aligned():
    def mock_run(cmd):
        if cmd == ["where", "python"]: return "C:\\Python39\\python.exe"
        if cmd == ["where", "pip"]: return "C:\\Python39\\Scripts\\pip.exe"
        return None
    with mock.patch("envfix.doctor._run_cmd", side_effect=mock_run):
        res = check_path()
        assert res.ok is True

def test_check_path_misaligned():
    def mock_run(cmd):
        if cmd == ["where", "python"]: return "C:\\Python39\\python.exe"
        if cmd == ["where", "pip"]: return "C:\\Users\\user\\myenv\\Scripts\\pip.exe"
        return None
    with mock.patch("envfix.doctor._run_cmd", side_effect=mock_run):
        res = check_path()
        assert res.ok is False
        assert "resolve to different environments" in res.warning
