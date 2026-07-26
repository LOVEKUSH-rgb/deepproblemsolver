# Contributing to envfix

Thanks for your interest in making `envfix` better! This is an early-stage
open-source project and all contributions are welcome.

---

## What we're looking for

- **New error patterns** — if envfix misdiagnosed an error type that has a
  well-known fix (e.g. a specific CUDA mismatch, a Node version conflict),
  a PR with a test case + expected fix is the best way to add it
- **Bug fixes** — especially around the fix normaliser (`_clean_fix`), the
  destructive-command guardrail, or the cache similarity threshold
- **Prompt improvements** — better Ollama prompts that produce more reliable
  `DIAGNOSIS/FIX` output across different model sizes
- **Non-Python / non-Windows fixes** — the tool was built on Windows but
  should work anywhere; PRs that fix macOS/Linux edge cases are welcome
- **Documentation** — clearer examples, better troubleshooting entries,
  translated READMEs

---

## Ground rules

1. **Don't rewrite what works.** Each phase of this tool was built
   incrementally. If you're adding a feature, build on top of the existing
   architecture (see the module breakdown below).
2. **All PRs must pass the test suite.** Run `python -m pytest tests/ -v`
   before opening a PR. No new tests = very likely to be rejected.
3. **Keep it offline-first.** `envfix` must work without any internet
   connection once Ollama is running. Don't add calls to external APIs.
4. **Don't add accounts or auth.** Per-user state is handled with OS
   usernames (`getpass.getuser()`). Keep it that way.

---

## Module map

| File | What it does |
|---|---|
| `envfix/main.py` | Typer CLI — `run` and `history` commands |
| `envfix/ai.py` | Builds the Ollama prompt, parses `DIAGNOSIS/FIX` |
| `envfix/runner.py` | Subprocess wrapper that captures stderr |
| `envfix/logger.py` | Per-user JSON log (reads + writes) |
| `envfix/cache.py` | Fuzzy-match cache — skips Ollama on repeat errors |
| `envfix/preview.py` | Dry-run descriptions + destructive command check |

---

## Local dev setup

```bash
git clone https://github.com/LOVEKUSH-rgb/deepproblemsolver.git
cd deepproblemsolver

# Install in editable mode (changes to source take effect immediately)
pip install -e .

# Run the full test suite (no Ollama needed)
python -m pytest tests/ -v

# Try it live (Ollama must be running)
envfix run python -m non_existent_module
```

---

## Submitting a PR

1. Fork the repo and create a branch: `git checkout -b fix/my-description`
2. Make your change + add/update tests
3. Run `python -m pytest tests/ -v` — all tests must pass
4. Open a PR with a clear description of *what* and *why*

If you're unsure whether an idea fits, open an issue first to discuss it.
