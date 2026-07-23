# envfix 🛠️

> **Automatically diagnose and fix Python/ML environment errors using a local LLM — fully offline, no paid API.**

When your `pip install`, PyTorch import, or CUDA setup fails, `envfix` catches the error, asks a local Ollama model what went wrong, proposes a one-liner fix, waits for your approval, runs it, and tells you if the original command now works.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Install Ollama](#1-install-ollama)
3. [Pull the model](#2-pull-the-model)
4. [Start the Ollama service](#3-start-the-ollama-service)
5. [Install envfix](#4-install-envfix)
6. [Usage](#usage)
7. [How it works](#how-it-works)
8. [Log file](#log-file)
9. [Running tests](#running-tests)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | ≥ 3.10 |
| pip | latest recommended |
| Ollama | latest |
| RAM | ≥ 8 GB (for `llama3.1:8b`) or ≥ 4 GB (for `qwen2.5:3b`) |

---

## 1. Install Ollama

**Windows / macOS / Linux** — download the installer from:

```
https://ollama.com/download
```

Or on Linux via the one-liner:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

---

## 2. Pull the model

After installing Ollama, pull whichever model fits your hardware:

```bash
# Recommended (needs ~8 GB RAM)
ollama pull llama3.1:8b

# Lighter alternatives (≥4 GB RAM)
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
```

---

## 3. Start the Ollama service

Ollama must be running in the background before you use `envfix`.

```bash
ollama serve
```

> **Tip:** On Windows, the Ollama installer adds a system tray icon that starts the service automatically on login.

---

## 4. Install envfix

Clone the repo and install in editable mode so the `envfix` command is registered globally (or in your active venv):

```bash
git clone https://github.com/<your-username>/envfix.git
cd envfix
pip install -e .
```

This installs two Python dependencies automatically:
- `typer[all]` — CLI framework + Rich for pretty terminal output
- `ollama` — Python client for the local Ollama service

---

## Usage

```
envfix run "<your failing command>"
```

### Examples

```bash
# Basic usage — wrap any failing command in quotes
envfix run "python -c 'import torch; print(torch.cuda.is_available())'"

# Works with pip, conda-style commands, script runs, etc.
envfix run "pip install -r requirements.txt"
envfix run "python train.py --gpu 0"

# Use a lighter model if your hardware is limited
envfix run "python setup_check.py" --model qwen2.5:3b
```

### What you'll see

```
▶ Running: python train.py --gpu 0

╭─────────────── ✗ Command Failed ───────────────╮
│ RuntimeError: CUDA error: no kernel image is   │
│ available for execution on the device          │
╰────────────────────────────────────────────────╯

🤖 Asking Ollama (llama3.1:8b) for a diagnosis…

╭──────────── envfix Suggestion ─────────────────╮
│ DIAGNOSIS                                      │
│ Your PyTorch build doesn't match the CUDA      │
│ driver version on this machine.                │
│                                                │
│ FIX                                            │
│ pip install torch --index-url                  │
│ https://download.pytorch.org/whl/cu118         │
╰────────────────────────────────────────────────╯

Run this fix? [y/N]:
```

---

## How it works

```
envfix run "cmd"
     │
     ▼
Run cmd via subprocess
     │
  failed? ──No──► exit 0 (all good)
     │
    Yes
     ▼
Send stderr to Ollama with structured prompt
     │
     ▼
Parse DIAGNOSIS + FIX from response
     │
     ▼
Display to user → ask "Run this fix? (y/n)"
     │
    Yes
     ▼
Run the fix command
     │
     ▼
Re-run original command
     │
     ▼
Report success/failure + write to envfix_log.json
```

---

## Log file

Every attempt (whether approved or not) is recorded to `envfix_log.json` in the directory where you run `envfix`. Each entry looks like:

```json
{
  "timestamp": "2026-07-23T17:45:00+00:00",
  "command": "python train.py",
  "stderr": "ModuleNotFoundError: No module named 'torch'",
  "diagnosis": "PyTorch is not installed in this environment.",
  "fix": "pip install torch",
  "approved": true,
  "worked": true
}
```

| Field | Meaning |
|---|---|
| `approved` | Did you say **y** to the fix? |
| `worked` | Did the original command succeed after the fix? |
| `worked: null` | Fix was not approved (no re-run attempted) |

---

## Running tests

```bash
# From the repo root
pip install pytest
python -m pytest tests/test_phase1.py -v
```

The test suite does **not** require Ollama to be running. It tests:
- The AI response parser (7 cases including edge cases)
- The subprocess runner (4 cases)
- The JSON logger (4 cases including corrupt-file recovery)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Error reaching Ollama: Connection refused` | Run `ollama serve` in a separate terminal |
| `model not found` | Run `ollama pull llama3.1:8b` (or your chosen model) |
| `envfix: command not found` | Run `pip install -e .` from the repo root |
| Model returns garbled output | Try `--model qwen2.5:3b`; raw output is shown instead of crashing |
| Fix runs but original still fails | The LLM diagnosis was wrong — try running again or fix manually |

---

## Future phases (not yet built)

- **Phase 2:** Dry-run preview before applying fixes; cache known error→fix pairs locally
- **Phase 3:** Share fix stats with classmates; track repeat usage
- **Phase 4:** Expand beyond Python/ML; per-user memory

---

## License

MIT
