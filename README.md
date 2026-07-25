# envfix 🛠️

> **Automatically diagnose and fix Python/ML environment errors using a local LLM — fully offline, no paid API.**

When your `pip install`, PyTorch import, or CUDA setup fails, `envfix` catches the error, asks a local [Ollama](https://ollama.com) model what went wrong, proposes a one-liner fix, waits for your approval, runs it, and tells you if the original command now works.

> ⚠️ **Early / experimental** — built for Python/ML environment errors. Feedback welcome via [GitHub Issues](https://github.com/LOVEKUSH-rgb/deepproblemsolver/issues).

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | ≥ 3.10 |
| [Ollama](https://ollama.com/download) | latest |
| RAM | ≥ 8 GB for `llama3.1:8b`  ·  ≥ 4 GB for `qwen2.5:3b` |

---

## Install

### Step 1 — Install Ollama

Download from **[ollama.com/download](https://ollama.com/download)** (Windows / macOS / Linux).

On Linux you can also run:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Step 2 — Pull a model

```bash
# Recommended (needs ~8 GB RAM)
ollama pull llama3.1:8b

# Lighter alternatives (≥ 4 GB RAM)
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
```

### Step 3 — Start the Ollama service

```bash
ollama serve
```

> **Windows tip:** The Ollama installer adds a system-tray icon that starts the service automatically on login — you can skip this step.

### Step 4 — Install envfix

```bash
git clone https://github.com/LOVEKUSH-rgb/deepproblemsolver.git
cd deepproblemsolver
pip install -e .
```

That's it. The `envfix` command is now available globally (or inside your active venv).

---

## Usage

```
envfix run <your failing command>
```

### Basic example

```bash
envfix run python train.py --gpu 0
```

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
│ python -m pip install torch --index-url        │
│ https://download.pytorch.org/whl/cu118         │
╰────────────────────────────────────────────────╯

📋 What this will do: Installs a package from PyPI

Run this fix? [y/n] (n):
```

### More examples

```bash
# Missing module
envfix run python -m non_existent_module_xyz

# Broken requirements file
envfix run python -m pip install -r requirements.txt

# Use a lighter model
envfix run python train.py --model qwen2.5:3b

# View past attempts
envfix history
envfix history --last 5
```

### Command reference

| Command | What it does |
|---|---|
| `envfix run <cmd>` | Run a command; diagnose + propose fix if it fails |
| `envfix run <cmd> --model <tag>` | Use a specific Ollama model |
| `envfix history` | Show the last 20 attempts from `envfix_log.json` |
| `envfix history --last N` | Show last N attempts |
| `envfix --help` | Full help |

---

## How it works

```
envfix run <cmd>
     │
     ▼
 Run cmd via subprocess
     │
  succeeded? ──Yes──► ✓ Nothing to fix
     │
    No
     ▼
 Check envfix_log.json for a similar past error (fuzzy match ≥ 85%)
     │
  Cache hit? ──Yes──► Show cached fix (skip model call)
     │
    No
     ▼
 Send stderr to Ollama with a structured prompt
     │
     ▼
 Parse DIAGNOSIS + FIX from the response
     │
     ▼
 Show dry-run description for risky commands (rm, setx, sudo …)
     │
     ▼
 Ask "Run this fix? [y/n]"
     │
    Yes
     ▼
 Apply fix → re-run original command
     │
     ▼
 Report success/failure + write to envfix_log.json
```

---

## Log file

Every attempt is recorded to `envfix_log.json` in the directory where you run `envfix`. The file is excluded from git via `.gitignore` so your personal error history never gets committed.

Each entry looks like:

```json
{
  "timestamp": "2026-07-25T14:45:00Z",
  "original_command": "python train.py --gpu 0",
  "error_text": "ModuleNotFoundError: No module named 'torch'",
  "diagnosis": "PyTorch is not installed in this environment.",
  "fix_command": "python -m pip install torch",
  "user_approved": true,
  "fix_worked": true,
  "source": "ollama"
}
```

| Field | Meaning |
|---|---|
| `user_approved` | Did you say **y** to the fix? |
| `fix_worked` | Did the original command succeed after the fix? |
| `fix_worked: null` | Fix was not approved — no retry attempted |
| `source` | `"ollama"` = fresh model call  ·  `"cache"` = reused from log |

---

## Running tests

```bash
# From the repo root — no Ollama needed
python -m pip install pytest
python -m pytest tests/ -v
```

The test suite (55 tests across 2 files) covers:

| Module | Tests |
|---|---|
| AI response parser | Strict format, case, whitespace, fallback |
| `_clean_fix()` normaliser | Backtick stripping, `pip` → `python -m pip` |
| Subprocess runner | Success, failure, stderr capture, bad commands |
| JSON logger | Schema, appending, corrupt-file recovery |
| Known-fix cache | Exact match, fuzzy match, Phase 1 compat, tier priority |
| Dry-run preview | Safe vs risky command classification |
| History reader | Ordering, Phase 1 normalisation, key presence |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Error reaching Ollama: Connection refused` | Run `ollama serve` in a separate terminal |
| `model "llama3.1:8b" not found` | Run `ollama pull llama3.1:8b` |
| `envfix: command not found` | Run `pip install -e .` from the repo root |
| Model returns garbled output | Try `--model qwen2.5:3b`; raw output is shown instead of crashing |
| `'pip' is not recognized` | Always use `python -m pip install …` on Windows |
| Fix runs but original still fails | The LLM diagnosis was wrong — try running again or fix manually |

---

## Roadmap

| Phase | Status |
|---|---|
| Phase 1 — Core loop: run → diagnose → fix → retry | ✅ Done |
| Phase 2 — Cache, dry-run preview, history command | ✅ Done |
| Phase 3 — Distribution, README, pyproject.toml | ✅ Done |
| Phase 4 — Multi-user memory, non-Python/ML errors | 🔜 Planned |

---

## License

MIT — see [LICENSE](LICENSE) or use freely.
