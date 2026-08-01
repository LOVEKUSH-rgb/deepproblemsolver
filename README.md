# envfix 🛠️
[![Tests](https://github.com/LOVEKUSH-rgb/deepproblemsolver/actions/workflows/tests.yml/badge.svg)](https://github.com/LOVEKUSH-rgb/deepproblemsolver/actions/workflows/tests.yml)

> **`envfix` wraps any failing shell command, asks a local AI model what went wrong, and proposes a one-click fix — fully offline, no API key, no cloud.**

```
without envfix                          with envfix
──────────────────────────────────────  ──────────────────────────────────────────
$ python train.py                       $ envfix run python train.py

ModuleNotFoundError:                    ✗ Command Failed
  No module named 'torch'              │ ModuleNotFoundError: No module named 'torch'

↓ Google the error                      🤖 Asking Ollama (llama3.1:8b)…
↓ Stack Overflow rabbit hole
↓ Try three different pip commands      ╭─────────── envfix Suggestion ────────────╮
↓ Wrong CUDA version                    │ DIAGNOSIS                                │
↓ Try again                             │ PyTorch is not installed in this env.    │
                                        │                                          │
~20 minutes later:                      │ FIX                                      │
$ python -m pip install torch           │ python -m pip install torch              │
                                        ╰──────────────────────────────────────────╯

                                        Run this fix? [y/n] (n): y
                                        ✓ Success! The fix resolved the issue.
                                        (total time: ~30 seconds)
```

> ⚠️ **Early / experimental.** Works best for common Python, Node.js, and
> package-manager errors. See [Known limitations](#known-limitations).

---

## Prerequisites

| Requirement | Version | Why |
|---|---|---|
| Python | ≥ 3.10 | f-strings, match syntax |
| [Ollama](https://ollama.com/download) | latest | (Optional) runs the local AI model |
| API Keys | | (Optional) `GROQ_API_KEY` or `GEMINI_API_KEY` for cloud models |
| RAM | ≥ 8 GB | for local `llama3.1:8b` — or ≥ 4 GB for `qwen2.5:3b` |

---

## Install

### Step 1 — Choose your AI provider

`envfix` supports local and cloud models. 

**Option A (Default): Local Ollama**
Download from **[ollama.com/download](https://ollama.com/download)** (Windows, macOS, Linux).

On Linux you can also run:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Step 2 — Pull a model

```bash
# Recommended (needs ~8 GB RAM free)
ollama pull llama3.1:8b

# Lighter alternatives if you have ≤ 4 GB free RAM
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
```

**Option B: Groq API (Cloud)**
1. Get a free API key from [console.groq.com](https://console.groq.com/).
2. Set it in your terminal:
   ```bash
   # Windows PowerShell
   $env:GROQ_API_KEY="your-key-here"
   # Linux/macOS
   export GROQ_API_KEY="your-key-here"
   ```

**Option C: Gemini API (Cloud)**
1. Get a free API key from [Google AI Studio](https://aistudio.google.com/).
2. Set it in your terminal:
   ```bash
   # Windows PowerShell
   $env:GEMINI_API_KEY="your-key-here"
   # Linux/macOS
   export GEMINI_API_KEY="your-key-here"
   ```

### Step 3 — Start Ollama

```bash
ollama serve
```

> **Windows tip:** The Ollama installer adds a system-tray icon that starts the
> service automatically on login — you may be able to skip this step.
> *(Skip this step if you are using Groq or Gemini).*

### Step 4 — Install envfix

```bash
git clone https://github.com/LOVEKUSH-rgb/deepproblemsolver.git
cd deepproblemsolver
pip install -e .
```

> **Why `-e`?** Editable mode means changes to the source code take effect
> immediately without reinstalling. For a "permanent" install just use
> `pip install .` instead.

Verify the install:
```bash
envfix --help
```

### Enable Shell Tab Completion

`envfix` supports tab completion for all common shells (bash, zsh, fish, PowerShell). To enable it, run:

```bash
envfix --install-completion
```

*Note: After running this command, you must restart your terminal or open a new tab for the completion to take effect. If you are using Windows/PowerShell, completion may have limited support depending on your execution policies.*

---

## 🚀 Quick start

```
envfix run <your failing command>
```



### Git Pre-commit Hook

`envfix` includes a built-in pre-commit hook that performs **ultra-fast local syntax checking** to catch broken code (like missing colons or parentheses) before it enters your commit history.

**Install the hook:**
```bash
envfix hook install
```

When you commit, the hook will use native `ast` parsing to instantly scan your staged `.py` files. *Note: `envfix hook-check` is designed to be near-instant and does NOT use AI or make network requests. It only validates code syntax locally.*

If an error is found, the commit will be blocked and you'll see a clear error:
`Hold on! file.py has a syntax error on line 42: '(' was never closed.`

**Uninstall the hook:**
```bash
envfix hook uninstall
```

### Common examples

```bash
# Missing Python module
envfix run python -m non_existent_module

# Broken requirements file
envfix run python -m pip install -r requirements.txt

# Node / npm error
envfix run npm run build --category node

# CUDA / GPU error
envfix run python train.py --gpu 0

# Use a lighter model on a low-RAM machine
envfix run python train.py --model qwen2.5:3b

# Use a cloud provider instead of local Ollama
envfix run npm install --provider groq
envfix run npm install --provider gemini

# Check your fix history
envfix history
envfix history --last 5
```

### What you'll see

```
▶ Running: python -m pip install -r requirements.txt

╭──────────── ✗ Command Failed ────────────╮
│ ERROR: Could not find a version that     │
│ satisfies the requirement bogus-pkg      │
╰──────────────────────────────────────────╯

🤖 Asking Ollama (llama3.1:8b) for a diagnosis…

╭────────── envfix Suggestion ─────────────╮
│ DIAGNOSIS                                │
│ The package 'bogus-pkg' does not exist   │
│ on PyPI.                                 │
│                                          │
│ FIX                                      │
│ python -m pip install <correct-name>     │
╰──────────────────────────────────────────╯

📋 What this will do: Installs a package from PyPI

Run this fix? [y/n] (n): y
```

If the same (or very similar) error has appeared before, `envfix` skips the
model call entirely and shows the cached suggestion instead:

```
⚡ Found a previously verified fix (97% match) — skipping model call.
```

If the suggested fix contains a destructive command (`rm -rf`, `sudo`,
`delete`, etc.), `envfix` shows an explicit warning and requires you to type
`yes` in full:

```
⚠️ DANGEROUS COMMAND DETECTED
This command may delete files, change permissions, or execute remote code.
Type 'yes' to run this fix (no):
```

### Command reference

| Command | What it does |
|---|---|
| `envfix run <cmd>` | Run a command; diagnose + suggest fix on failure |
| `envfix run <cmd> --provider <name>` | Select AI provider (`ollama` [default], `groq`, `gemini`) |
| `envfix run <cmd> --model <tag>` | Use a specific model tag/name for the chosen provider |
| `envfix run <cmd> --category <eco>` | Hint the ecosystem (`python`, `node`, `docker` …) |
| `envfix history` | Show the last 20 attempts |
| `envfix history --last N` | Show last N attempts |

---

## How it works

```
envfix run <cmd>
     │
     ▼
 subprocess: run the command, capture stderr
     │
  succeeded? ──Yes──► ✓ Nothing to fix
     │
    No
     ▼
 Check per-user log (envfix_log_<username>.json) for similar past error
     │
  Cache hit ──Yes──► Show cached fix (skip Ollama)
     │
    No
     ▼
 Build structured prompt → POST to local Ollama service
     │
     ▼
 Parse DIAGNOSIS + FIX from model response
     │
     ▼
 Dry-run description for non-obvious commands
 Destructive guard for dangerous commands (requires "yes" in full)
     │
     ▼
 User approves → apply fix → re-run original command
     │
     ▼
 Log result to envfix_log_<username>.json
```

---

### Supported Ecosystems

`envfix` automatically detects and diagnoses errors in:
- **Python**: pip, pytest, python scripts
- **Node.js**: npm, yarn, node scripts
- **Rust (Cargo)**: rustc compilation, missing crates
- **Go**: go modules, compiler errors
- **Java**: Maven, Gradle, JVM stack traces
- **Docker**: Dockerfile build steps
- **General CLI**: bash, powershell, missing binaries, permission issues

When you run `envfix`, it isolates code snippets from the stack trace and feeds them into the local model for a targeted diagnosis.

```bash
# Python
envfix run "pytest tests/" --category python

# Rust
envfix run "cargo build" --category rust

# Go
envfix run "go run main.go" --category go

# Docker
envfix run "docker build -t my-app ." --category docker
```

---

## Per-user history

Every attempt is logged to `envfix_log_<username>.json` in the directory where
you run `envfix`. Each user on the same machine gets their own separate file —
no shared state, no accounts.

The file is excluded from git by `.gitignore` so your personal history never
gets committed.

Sample entry:
```json
{
  "timestamp": "2026-07-26T08:00:00Z",
  "original_command": "python train.py",
  "error_text": "ModuleNotFoundError: No module named 'torch'",
  "diagnosis": "PyTorch is not installed in this environment.",
  "fix_command": "python -m pip install torch",
  "user_approved": true,
  "fix_worked": true,
  "source": "ollama",
  "category": "python",
  "context_included": false,
  "provider": "ollama"
}
```

---

## Opt-In Team Telemetry

`envfix` supports sending optional, anonymous telemetry to a centralized team dashboard (if configured) so that engineering leads can view aggregated metrics like the most frequent errors and overall AI success rate. 

**By default, telemetry is OFF.** `envfix` runs fully offline and does not send any data to any external server. 

To enable telemetry, provide your team's API key and backend URL using environment variables:
```bash
export ENVFIX_TEAM_API_KEY="your-team-api-key"
export ENVFIX_BACKEND_URL="http://your-backend-domain.com"
```
Alternatively, these can be set in the `~/.envfix/config.toml` file (`team_api_key` and `backend_url`).

If configured, `envfix` will send a non-blocking background request to the backend with the following minimal usage statistics:
- `error_type`: A short summary of the error (e.g. `ZeroDivisionError`). No private code or logs are sent.
- `provider_used`: The AI provider queried (e.g. `groq`, `ollama`).
- `was_cache_hit`: `true` if the local cache handled the fix without a model call.
- `fix_applied`: `true` if the user approved running the fix.
- `fix_worked`: `true` if the retry was successful.

If the network request fails, `envfix` will silently swallow the error to guarantee zero interruptions to your workflow.

---

## Security & Data Redaction

Before any error text, stack trace, or code snippet is logged locally or sent to an AI provider (Ollama, Groq, Gemini), `envfix` runs it through a **best-effort Secret Redaction Layer**. 

This layer aggressively searches for and redacts:
- **AWS Access Keys**
- **JWT Tokens**
- **Database Connection URLs** (the password segment is masked)
- **Private Key Blocks** (e.g. RSA / ECDSA keys)
- **Generic Secrets** (strings > 20 characters assigned to variables named API_KEY, SECRET, TOKEN, PASSWORD, etc.)

Any detected secrets are replaced with placeholders like `[REDACTED:AWS_KEY]`.

> **Note:** This is purely pattern-based matching and is **not a guarantee**. You should always avoid committing secrets to code or printing them in logs in the first place.

---

## Known limitations

- **Model quality varies.** envfix is only as good as the model 
  behind it. Smaller local models (`qwen2.5:3b`, `llama3.2:3b`) 
  sometimes produce vague or incorrect diagnoses for complex errors 
  — envfix now warns you when a small model is selected. 
  `llama3.1:8b` is the recommended local minimum; a cloud provider 
  (Groq, Gemini) will generally be more reliable for tricky cases.

- **Project-specific errors are more accurate with indexing.** Run 
  `envfix index` once in your project root and envfix will pull in 
  relevant snippets from your own codebase when diagnosing errors, 
  not just generic patterns. Without an index — or for very obscure 
  issues (e.g. a bug inside a custom C extension) — suggestions will 
  be more generic.

- **Code bugs vs. environment issues.** envfix classifies errors as 
  either environment/dependency issues (fixable with a command) or 
  code-logic bugs (a typo, undefined variable, etc. — not fixable 
  by any terminal command). For Python and Node.js, this 
  classification is backed by a pattern-matching safety net in 
  addition to the AI's own judgment; for Rust, Go, and Java it 
  currently relies on the AI's classification alone.

- **Single fix per failure.** envfix proposes one fix at a time. If 
  it doesn't work, run `envfix run <cmd>` again — the model may 
  suggest something different on a second attempt.

- **Still early for some ecosystems.** Prompt tuning and the 
  fuzzy-match cache were built and tested primarily against Python 
  and Node.js errors. Rust, Go, Java, and Docker error detection is 
  implemented but has not yet been verified against real errors in 
  those ecosystems — treat it as early and unproven until tested 
  further.

---

## Running the tests

```bash
# No Ollama needed — all tests are offline
python -m pytest tests/ -v
```

67 tests across three files covering the AI parser, subprocess runner, JSON
logger, two-tier cache, dry-run preview, safety guardrails, and per-category
matching.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Error reaching Ollama: Connection refused` | Run `ollama serve` in a separate terminal |
| `model "llama3.1:8b" not found` | Run `ollama pull llama3.1:8b` |
| `envfix: command not found` | Run `pip install -e .` from the repo root |
| Fix runs but original still fails | The model diagnosis was wrong — run again or fix manually |
| Model returns garbled output | Try `--model qwen2.5:3b` |
| Always shows cached (wrong) fix | Cache threshold is 0.85; if the fix is wrong, say `n` and re-run — Ollama will be called fresh |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the module map, ground rules, and
how to submit a fix.

---

## License

This project is licensed under the Business Source License 1.1 (BSL 1.1). 
It requires a commercial license for enterprise/managed service use. 
See the [LICENSE](LICENSE) file for complete details.
