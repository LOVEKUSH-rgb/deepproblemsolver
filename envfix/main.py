"""main.py — Typer CLI entry point for envfix (Phase 2)."""

import sys
import os
from datetime import datetime, timezone
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from envfix.ai import _clean_fix, get_actual_model, get_diagnosis
from envfix.cache import find_cached_fix
from envfix.config import load_config, save_config, reset_config
from envfix.context import extract_context, trim_stack_trace
from envfix.logger import LOG_FILE, get_history, get_log_file, log_attempt
from envfix.telemetry import send_telemetry
from envfix.redact import redact_secrets, redact_secrets_with_count
from envfix.signature import generate_signature
from envfix.preview import get_fix_preview, is_destructive
from envfix.runner import run_command

from envfix.dependencies import (
    extract_package_name,
    update_requirements_txt,
    update_pyproject_toml,
)
from envfix.git_utils import (
    is_in_git_repo,
    has_uncommitted_changes,
    create_safety_stash,
)
from envfix.doctor import run_all_checks, CheckResult
from envfix.ai import get_doctor_fix

app = typer.Typer(
    name="envfix",
    help="Diagnose and auto-fix Python/ML environment errors using a local LLM.",
    pretty_exceptions_enable=False
)

from envfix.hook import hook_app, run_hook_check
app.add_typer(hook_app)

@app.command("hook-check", hidden=True)
def hook_check_cmd() -> None:
    """Internal fast syntax checker run by the pre-commit hook."""
    run_hook_check()

console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

_ollama_warning_printed = False

def _print_ollama_warning_if_needed(provider: str, model: str) -> None:
    global _ollama_warning_printed
    if not _ollama_warning_printed and provider.lower() == "ollama" and "3b" in model.lower():
        console.print(
            "\n[dim yellow]Note: smaller local models (3B parameters) may give vague or "
            "incorrect diagnoses for complex errors. llama3.1:8b or a cloud "
            "provider is recommended for tricky cases.[/dim yellow]"
        )
        _ollama_warning_printed = True


def _quote_join(tokens: List[str]) -> str:
    """
    Join command tokens back into a shell string, re-quoting any token
    that contains spaces with double quotes.

    PowerShell strips quotes when it passes arguments, so:
        envfix run python -c "import torch"
    arrives as tokens: ["python", "-c", "import torch"]

    Without re-quoting we'd produce: python -c import torch  (SyntaxError).
    With re-quoting we produce:      python -c "import torch"  (correct).
    """
    if len(tokens) == 1:
        return tokens[0]

    parts = []
    for tok in tokens:
        if " " in tok:
            tok = '"' + tok.replace('"', '\\"') + '"'
        parts.append(tok)
    return " ".join(parts)


def _show_fix_panel(
    diagnosis: str,
    fix: str,
    source: str,
    cache_score: Optional[float] = None,
) -> None:
    """Render the DIAGNOSIS + FIX suggestion panel."""
    source_tag = (
        f"[dim] (from cache — {cache_score:.0%} match)[/dim]"
        if source == "cache" and cache_score is not None
        else ""
    )
    console.print(
        Panel(
            Text.assemble(
                ("DIAGNOSIS\n", "bold magenta"),
                (diagnosis + "\n\n", "white"),
                ("FIX\n", "bold cyan"),
                (fix, "bold white"),
            ),
            title=f"[bold]envfix Suggestion[/bold]{source_tag}",
            border_style="cyan",
            expand=False,
        )
    )


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command("config")
def config_cmd(
    show: bool = typer.Option(False, "--show", help="Show current configuration."),
    reset: bool = typer.Option(False, "--reset", help="Reset configuration to defaults."),
    local_only: Optional[str] = typer.Option(None, "--local-only", help="Enable or disable strict local-only mode (true/false)."),
    contribute_to_community: Optional[str] = typer.Option(None, "--contribute-to-community", help="Enable or disable anonymous community error database (true/false)."),
) -> None:
    """Manage envfix global configuration interactively."""
    if reset:
        reset_config()
        console.print("[green]Configuration reset to defaults.[/green]")
        return
        
    if show:
        config = load_config()
        if not config:
            console.print("[yellow]No configuration found. Using hardcoded defaults.[/yellow]")
            return
            
        table = Table(title="Global Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="magenta")
        
        for k, v in config.items():
            table.add_row(k, str(v))
            
        console.print(table)
        return

    if local_only is not None or contribute_to_community is not None:
        config_data = load_config()
        if local_only is not None:
            local_only_val = local_only.strip().lower() == "true"
            config_data["local_only"] = local_only_val
            mode = "ENABLED" if local_only_val else "DISABLED"
            console.print(f"\n[bold green]Local-only mode {mode}.[/bold green]")
        
        if contribute_to_community is not None:
            contrib_val = contribute_to_community.strip().lower() == "true"
            config_data["contribute_to_community"] = contrib_val
            mode = "ENABLED" if contrib_val else "DISABLED"
            console.print(f"\n[bold green]Community contribution {mode}.[/bold green]")
            
        save_config(config_data)
        return

    console.print("[bold cyan]envfix Configuration Setup[/bold cyan]\n")
    
    while True:
        provider = typer.prompt("Default provider [ollama/groq/gemini]", default="ollama")
        if provider in ["ollama", "groq", "gemini"]:
            break
        console.print("[red]Invalid choice. Must be ollama, groq, or gemini.[/red]")
        
    while True:
        category = typer.prompt("Default category [general/python/node/docker]", default="general")
        if category in ["general", "python", "node", "docker"]:
            break
        console.print("[red]Invalid choice. Must be general, python, node, or docker.[/red]")
    
    save_config({
        "default_provider": provider,
        "default_category": category,
        "local_only": load_config().get("local_only", False)
    })
    
    console.print("\n[bold green]Configuration saved successfully![/bold green]")


@app.command("doctor")
def doctor_cmd(
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Model tag to use for diagnosis.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="AI provider to use (ollama, groq, gemini).",
    ),
    gpu: bool = typer.Option(False, "--gpu", help="Run only GPU/CUDA checks."),
    docker: bool = typer.Option(False, "--docker", help="Run only Docker checks."),
    python: bool = typer.Option(False, "--python", help="Run only Python checks."),
    node: bool = typer.Option(False, "--node", help="Run only Node.js checks."),
    conda: bool = typer.Option(False, "--conda", help="Run only Conda checks."),
    path: bool = typer.Option(False, "--path", help="Run only PATH checks."),
    danger_override: bool = typer.Option(
        False,
        "--danger-override",
        help="Bypass the git safety halt when outside a repository.",
    ),
) -> None:
    """Report the current operating mode and proactive system compatibility checks."""
    config = load_config()
    is_local = str(config.get("local_only", "")).lower() == "true" or config.get("local_only") is True
    
    if not provider:
        provider = config.get("default_provider", "ollama")
    if not model:
        model = config.get("default_model", "llama3.1:8b")
        
    console.print("\n[bold cyan]envfix Doctor[/bold cyan]\n")
    
    if is_local:
        console.print("[bold green]Local-only mode: ENABLED - no data leaves this machine except to your local Ollama instance.[/bold green]\n")
        if provider.lower() in ["groq", "gemini"]:
            console.print("[bold red]Error:[/bold red] Local-only mode is enabled; cloud providers are disabled.")
            raise typer.Exit(code=1)
    else:
        console.print("[bold yellow]Local-only mode: DISABLED - cloud telemetry or cloud AI providers may be used if configured.[/bold yellow]\n")

    console.print("[bold]Running Environment Checks...[/bold]")
    
    run_all = not any([gpu, docker, python, node, conda, path])
    checks = run_all_checks(
        run_python=python or run_all,
        run_node=node or run_all,
        run_gpu=gpu or run_all,
        run_docker=docker or run_all,
        run_conda=conda or run_all,
        run_path=path or run_all,
    )
    
    warnings = []
    
    for check in checks:
        if check.ok and not check.warning:
            version_str = f" {check.version}" if check.version else ""
            details_str = f" ({check.details})" if check.details else ""
            console.print(f"[green][OK][/green] {check.name}{version_str}{details_str} - OK")
        elif check.warning:
            console.print(f"[bold yellow][WARNING][/bold yellow] [yellow]{check.warning} - potential compatibility issue[/yellow]")
            warnings.append(check)
        else:
            console.print(f"[red][ERROR][/red] [red]{check.warning}[/red]")
            
    if not warnings:
        console.print("\n[bold green][OK] All checks passed - environment looks healthy[/bold green]")
        return
        
    console.print("\n[bold]Consulting AI for explanations and fixes...[/bold]")
    proposed_fixes = []
    
    for check in warnings:
        try:
            _print_ollama_warning_if_needed(provider, get_actual_model(model, provider))
            result = get_doctor_fix(
                conflict_details=check.warning,
                model=model,
                provider=provider
            )
            proposed_fixes.append({
                "check": check,
                "diagnosis": result.diagnosis,
                "fix": result.fix,
                "raw_response": result.raw_response
            })
            _show_fix_panel(result.diagnosis, result.fix, provider)
        except Exception as exc:
            console.print(f"[bold red]Error reaching {provider} for {check.name}:[/bold red] {exc}")
            
    if not proposed_fixes:
        return
        
    approved = Confirm.ask("\n[bold]Fix all detected issues?[/bold]", default=False)
    
    if not approved:
        console.print("[dim]Exiting without changes.[/dim]")
        for pf in proposed_fixes:
            log_attempt(
                original_command="envfix doctor",
                error_text=pf["check"].warning,
                diagnosis=pf["diagnosis"],
                fix_command=pf["fix"],
                user_approved=False,
                fix_worked=None,
                source=provider,
                category="doctor_scan",
                provider=provider,
                entry_type="doctor_scan"
            )
        return
        
    # Git Safety Backup
    stash_created = False
    if not is_in_git_repo():
        if not danger_override:
            console.print(
                "[bold red]Safety halt: You are not in a Git repository. envfix cannot "
                "guarantee safe rollbacks here. Commit your work to git first, or "
                "run with --danger-override to proceed anyway.[/bold red]\n"
            )
            raise typer.Exit(code=1)
        else:
            console.print(
                "[bold yellow]Warning: not in a git repository. envfix cannot create "
                "a safety backup before applying fixes. Proceeding via --danger-override.[/bold yellow]\n"
            )
    elif has_uncommitted_changes():
        if create_safety_stash():
            stash_created = True

    # Execute fixes sequentially
    for pf in proposed_fixes:
        fix_cmd = pf["fix"]
        if fix_cmd.strip() == "None (Code change required)":
            console.print(f"\n[bold yellow][WARNING] Skipping {pf['check'].name}:[/bold yellow] Manual code change required.")
            continue
            
        console.print(f"\n[bold cyan]⚙ Applying fix for {pf['check'].name}:[/bold cyan] {fix_cmd}")
        fix_stdout, fix_stderr, fix_rc = run_command(fix_cmd)
        
        if fix_stdout:
            console.print(fix_stdout, end="")
        if fix_stderr:
            console.print(fix_stderr, end="")
            
        worked = (fix_rc == 0)
        if worked:
            console.print(f"[bold green][OK] Fix applied successfully.[/bold green]")
        else:
            console.print(f"[bold red][ERROR] Fix failed (exit code {fix_rc}).[/bold red]")
            
        log_attempt(
            original_command="envfix doctor",
            error_text=pf["check"].warning,
            diagnosis=pf["diagnosis"],
            fix_command=fix_cmd,
            user_approved=True,
            fix_worked=worked,
            source=provider,
            category="doctor_scan",
            provider=provider,
            entry_type="doctor_scan"
        )
        
    if stash_created:
        console.print(
            "\n[bold cyan]A safety backup was created. If these fixes caused "
            "problems, run: git stash pop[/bold cyan]"
        )


def _is_code_logic_exception(error_text: str, category: str) -> bool:
    """Check if the error matches known language-specific code-logic error patterns."""
    cat = category.lower()
    
    if cat == "python":
        return bool(re.search(r'(NameError|SyntaxError|IndentationError|AttributeError|TypeError):', error_text))
    elif cat in ("node", "javascript", "js", "typescript", "ts"):
        # Explicitly exclude environment issues (missing modules, missing files)
        if re.search(r"(Cannot find module|MODULE_NOT_FOUND|ENOENT)", error_text):
            return False
        return bool(re.search(r'(ReferenceError|SyntaxError|TypeError):', error_text))
    elif cat == "rust":
        return bool(re.search(r'error\[E[0-9]+\]: cannot find (value|function) .* in this scope|expected .*, found .*', error_text))
    elif cat == "java":
        return bool(re.search(r'error: cannot find symbol|java\.lang\.NullPointerException', error_text))
    elif cat == "go":
        return bool(re.search(r'undefined: .*|.* declared and not used', error_text))
        
    return False


@app.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def run(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Model tag to use for diagnosis. [default: llama3.1:8b (or config)]",
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category",
        help="Ecosystem category (e.g. python, node, docker) to tailor the diagnosis. [default: general (or config)]",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="AI provider to use (ollama, groq, gemini). [default: ollama (or config)]",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Bypass the local cache and force a new AI diagnosis.",
    ),
    danger_override: bool = typer.Option(
        False,
        "--danger-override",
        help="Bypass the git safety halt when outside a repository.",
    ),
) -> None:
    """
    Run COMMAND. If it fails, diagnose the error with a local LLM (or cache),
    propose a fix, and (with your approval) apply it and retry.

    Everything after [OPTIONS] is treated as the command to run:

    \b
        envfix run python -m non_existent_module_xyz
        envfix run python -c "import torch"
        envfix run python train.py --gpu 0
        envfix run --model qwen2.5:3b python train.py
    """
    # ── Parse args (strip Typer 0.27 subcommand-name leak) ───────────────
    args = list(ctx.args)
    if args and args[0] == "run":
        args.pop(0)
    cmd = _quote_join(args)

    if not cmd.strip():
        console.print(
            "[bold red]Error:[/bold red] No command provided.\n"
            "Usage:  [bold]envfix run[/bold] [OPTIONS] COMMAND...\n"
            "Example:[bold] envfix run python -m non_existent_module_xyz[/bold]"
        )
        raise typer.Exit(code=1)
        
    # Resolve defaults from config if omitted
    config = load_config()
    if not provider:
        provider = config.get("default_provider", "ollama")
    if not category:
        category = config.get("default_category", "general")
    if not model:
        model = config.get("default_model", "llama3.1:8b")

    is_local = str(config.get("local_only", "")).lower() == "true" or config.get("local_only") is True
    if is_local and provider.lower() in ["groq", "gemini"]:
        console.print("[bold red]Error:[/bold red] Local-only mode is enabled; cloud providers are disabled. Disable local-only mode to use cloud providers.")
        raise typer.Exit(code=1)

    # ── Step 1: Run the original command ─────────────────────────────────
    console.print(f"\n[bold cyan]> Running:[/bold cyan] {cmd}\n")
    stdout, stderr, returncode = run_command(cmd)

    if stdout:
        console.print(stdout, end="")

    if returncode == 0:
        console.print("\n[bold green]✓ Command succeeded — nothing to fix![/bold green]")
        return

    # ── Step 2: Command failed — show the error ───────────────────────────
    error_text, secrets_count1 = redact_secrets_with_count(stderr.strip() or stdout.strip() or "(no output captured)")
    console.print(
        Panel(
            error_text,
            title="[bold red][X] Command Failed[/bold red]",
            border_style="red",
            expand=False,
        )
    )

    # ── Step 3: Extract code context from the stack trace ─────────────────
    code_context = extract_context(error_text)
    if code_context:
        console.print(
            f"[dim][Context] Context found: {code_context.filepath} "
            f"(lines {code_context.start_line}-{code_context.end_line})[/dim]"
        )

    # ── Step 4: Check known-fix cache before calling the model ───────────
    if not no_cache:
        cache_hit = find_cached_fix(error_text, category=category)
    else:
        cache_hit = None
    
    source = provider
    classification = "UNKNOWN"
    mismatch_flagged = False

    if cache_hit:
        if cache_hit.previously_worked:
            banner = (
                f"[Cache] Found a previously [bold green]verified[/bold green] fix "
                f"for a similar error ({cache_hit.score:.0%} match) - skipping model call."
            )
        else:
            banner = (
                f"[Cache] Found a previously [bold yellow]attempted[/bold yellow] fix "
                f"for a similar error ({cache_hit.score:.0%} match) - "
                "skipping model call. [dim](fix didn't fully resolve it last time)[/dim]"
            )
        console.print(f"\n{banner}")
        diagnosis = cache_hit.diagnosis
        # Normalise cached fix commands — old log entries may have bare 'pip install'
        # which doesn't work on Windows. _clean_fix() converts it to 'python -m pip'.
        fix = _clean_fix(cache_hit.fix)
        source = "cache"
        _show_fix_panel(diagnosis, fix, source, cache_hit.score)
    else:
        community_hit = False
        if config.get("contribute_to_community"):
            sig = generate_signature(error_text, category)
            try:
                backend_url = config.get("backend_url", "http://localhost:8000")
                import requests
                resp = requests.get(f"{backend_url}/community/lookup", params={"signature": sig, "category": category}, timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    diagnosis = "Community-sourced fix"
                    fix = _clean_fix(data["fix_command"])
                    source = "community"
                    rate = data["success_rate"]
                    samples = data["sample_size"]
                    banner = f"[Community] Found a community fix with {rate:.0%} success across {samples} reports!"
                    console.print(f"\n[bold green]{banner}[/bold green]")
                    _show_fix_panel(diagnosis, fix, source, rate)
                    community_hit = True
            except Exception:
                pass
                
        if not community_hit:
            # ── Step 4a: Ask the LLM ─────────────────────────────────────────
            provider_name = provider.capitalize()
            display_model = get_actual_model(model, provider)
            
            _print_ollama_warning_if_needed(provider, display_model)
            
            console.print(
                f"\n[bold yellow][AI] Asking {provider_name} ({display_model}) for a diagnosis...[/bold yellow]"
            )
            try:
                trimmed_error = trim_stack_trace(
                    error_text,
                    ignore_patterns=config.get("ignore_patterns", [])
                )
                result = get_diagnosis(
                    stderr=trimmed_error,
                    model=model,
                    category=category,
                    code_context=code_context,
                    provider=provider,
                )
            except RuntimeError as exc:
                if str(exc).startswith("[!]"):
                    console.print(f"\n[bold red]{exc}[/bold red]")
                else:
                    console.print(f"\n[bold red]Error reaching {provider_name}:[/bold red] {exc}")
                raise typer.Exit(code=1)
    
            if not result.parsed_ok:
                console.print(
                    "\n[bold yellow][Warning] Could not parse a structured response. "
                    "Showing raw model output:[/bold yellow]"
                )
                console.print(
                    Panel(result.raw_response, border_style="yellow", expand=False)
                )
                log_attempt(
                    original_command=redact_secrets(cmd),
                    redacted_secrets_count=locals().get('secrets_count1', 0) + locals().get('secrets_count2', 0),
                    error_text=error_text,
                    diagnosis=result.diagnosis,
                    fix_command=result.fix,
                    user_approved=False,
                    fix_worked=None,
                    source=provider,
                    category=category,
                    context_included=code_context is not None,
                    provider=provider,
                    classification=result.classification,
                    mismatch_flagged=result.mismatch_flagged,
                )
                raise typer.Exit(code=1)
    
            diagnosis = result.diagnosis
            fix = result.fix
            classification = result.classification
            mismatch_flagged = False

            if _is_code_logic_exception(error_text, category):
                if classification != "CODE_ISSUE" or fix != "NONE":
                    mismatch_flagged = True
                    result.mismatch_flagged = True
                    console.print("\n[bold yellow]⚠ This suggested fix may not address the actual error type — review before running[/bold yellow]")

            if fix != "NONE":
                _show_fix_panel(diagnosis, fix, source)

    # ── Step 4b: Dry-run preview ──────────────────────────────────────────
    if fix.strip() == "NONE":
        console.print("\n[bold yellow][Code Issue] This looks like a bug in your code, not an environment problem:[/bold yellow]")
        console.print(f"[dim]{diagnosis}[/dim]")
        
        log_attempt(
            original_command=redact_secrets(cmd),
        redacted_secrets_count=locals().get('secrets_count1', 0) + locals().get('secrets_count2', 0),
            error_text=error_text,
            diagnosis=diagnosis,
            fix_command=fix,
            user_approved=False,
            fix_worked=None,
            source=source,
            category=category,
            context_included=code_context is not None,
            provider=provider,
            classification=classification,
            mismatch_flagged=mismatch_flagged,
        )
        raise typer.Exit(code=1)

    preview = get_fix_preview(fix)
    if preview:
        console.print(
            f"\n[bold yellow]📋 What this will do:[/bold yellow] {preview}"
        )

    # ── Step 5: Ask for approval ──────────────────────────────────────────
    if is_destructive(fix):
        console.print(
            "\n[bold red]⚠️ DANGEROUS COMMAND DETECTED[/bold red]\n"
            "[yellow]This command may delete files, change permissions, or execute remote code.[/yellow]"
        )
        response = Prompt.ask("[bold]Type 'yes' to run this fix[/bold]", default="no")
        approved = (response.strip().lower() == "yes")
    else:
        approved = Confirm.ask("\n[bold]Run this fix?[/bold]", default=False)

    if not approved:
        console.print("[dim]Exiting without changes.[/dim]")
        log_attempt(
            original_command=redact_secrets(cmd),
        redacted_secrets_count=locals().get('secrets_count1', 0) + locals().get('secrets_count2', 0),
            error_text=error_text,
            diagnosis=diagnosis,
            fix_command=fix,
            user_approved=False,
            fix_worked=None,
            source=source,
            category=category,
            context_included=code_context is not None,
            provider=provider,
            classification=classification,
            mismatch_flagged=mismatch_flagged,
        )
        raise typer.Exit(code=0)

    # ── Git Safety Backup ──────────────────────────────────────────────────
    stash_created = False
    if not is_in_git_repo():
        if not danger_override:
            console.print(
                "[bold red]Safety halt: You are not in a Git repository. envfix cannot "
                "guarantee safe rollbacks here. Commit your work to git first, or "
                "run with --danger-override to proceed anyway.[/bold red]\n"
            )
            raise typer.Exit(code=1)
        else:
            console.print(
                "[bold yellow]Warning: not in a git repository. envfix cannot create "
                "a safety backup before applying fixes. Proceeding via --danger-override.[/bold yellow]\n"
            )
    elif has_uncommitted_changes():
        if create_safety_stash():
            stash_created = True

    # ── Step 6: Run the fix, then re-run the original command ─────────────
    console.print(f"\n[bold cyan]⚙ Applying fix:[/bold cyan] {fix}\n")
    fix_stdout, fix_stderr, fix_rc = run_command(fix)

    if fix_stdout:
        console.print(fix_stdout, end="")
    if fix_stderr:
        console.print(fix_stderr, end="")

    if fix_rc != 0:
        console.print(
            "[bold red][X] Fix command itself failed "
            f"(exit code {fix_rc}). Aborting retry.[/bold red]"
        )
        log_attempt(
            original_command=redact_secrets(cmd),
            redacted_secrets_count=locals().get('secrets_count1', 0) + locals().get('secrets_count2', 0),
            error_text=error_text,
            diagnosis=diagnosis,
            fix_command=fix,
            user_approved=True,
            fix_worked=False,
            source=source,
            category=category,
            context_included=code_context is not None,
            provider=provider,
            classification=classification,
            mismatch_flagged=mismatch_flagged,
        )
        raise typer.Exit(code=1)

    console.print(
        f"\n[bold cyan]🔄 Re-running original command:[/bold cyan] {cmd}\n"
    )
    retry_stdout, retry_stderr, retry_rc = run_command(cmd)

    if retry_stdout:
        console.print(retry_stdout, end="")
    if retry_stderr:
        console.print(retry_stderr, end="")

    # ── Step 7: Report result ─────────────────────────────────────────────
    worked = retry_rc == 0
    if worked:
        console.print(
            "\n[bold green]✓ Success! The fix resolved the issue.[/bold green]"
        )
        
        # ── Dependency auto-append feature ──────────────────────────────────────
        if "ModuleNotFoundError" in error_text or "ImportError" in error_text:
            pkg = extract_package_name(fix)
            if pkg:
                # Check for pyproject.toml
                pyproject_path = os.path.join(os.getcwd(), "pyproject.toml")
                req_path = os.path.join(os.getcwd(), "requirements.txt")
                
                if os.path.exists(pyproject_path):
                    if Confirm.ask(f"\n[bold]Also add '{pkg}' to pyproject.toml?[/bold]", default=False):
                        update_pyproject_toml(pyproject_path, pkg)
                        console.print(f"[dim]Added {pkg} to pyproject.toml.[/dim]")
                elif os.path.exists(req_path):
                    if Confirm.ask(f"\n[bold]Also add '{pkg}' to requirements.txt?[/bold]", default=False):
                        update_requirements_txt(req_path, pkg)
                        console.print(f"[dim]Added {pkg} to requirements.txt.[/dim]")
                        
        # ── Post Fix Hook ───────────────────────────────────────────────────────
        hook = config.get("post_fix_hook")
        if hook:
            console.print(f"\n[bold magenta][Hook] Running post-fix hook:[/bold magenta] {hook}")
            hook_stdout, hook_stderr, _ = run_command(hook)
            if hook_stdout:
                console.print(hook_stdout, end="")
            if hook_stderr:
                console.print(hook_stderr, end="")
    else:
        console.print(
            "\n[bold red][X] Original command still failed after the fix "
            f"(exit code {retry_rc}). "
            "You may need to try a different approach.[/bold red]"
        )

    if stash_created:
        console.print(
            "\n[bold cyan]A safety backup was created. If this fix caused "
            "problems, run: git stash pop[/bold cyan]"
        )

    # ── Step 8: Log everything ────────────────────────────────────────────
    log_attempt(
        original_command=redact_secrets(cmd),
        redacted_secrets_count=locals().get('secrets_count1', 0) + locals().get('secrets_count2', 0),
        error_text=error_text,
        diagnosis=diagnosis,
        fix_command=fix,
        user_approved=True,
        fix_worked=worked,
        source=source,
        category=category,
        context_included=code_context is not None,
        provider=provider,
        classification=classification,
        mismatch_flagged=mismatch_flagged,
    )
    console.print(f"\n[dim][Log] Attempt logged to {get_log_file()}[/dim]")
    
    if config.get("contribute_to_community"):
        try:
            sig = generate_signature(error_text, category)
            backend_url = config.get("backend_url", "http://localhost:8000")
            import requests
            requests.post(
                f"{backend_url}/community/report",
                json={
                    "signature": sig,
                    "category": category,
                    "fix_command": fix,
                    "worked": worked
                },
                timeout=3
            )
        except Exception:
            pass # Fail silently if backend is unavailable

    raise typer.Exit(code=0 if worked else 1)


@app.command("diagnose")
def diagnose_cmd(
    log_file: str = typer.Argument(
        ...,
        help="Path to the file containing the failed test/build logs.",
    ),
    ci: bool = typer.Option(
        False,
        "--ci",
        help="Output raw Markdown suitable for a CI/CD pipeline (e.g. GitHub PR comment).",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help="Model tag to use for diagnosis.",
    ),
    category: Optional[str] = typer.Option(
        None,
        "--category",
        help="Ecosystem category.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="AI provider to use (ollama, groq, gemini).",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Bypass the local cache and force a new AI diagnosis.",
    ),
    output_file: Optional[str] = typer.Option(
        None,
        "--output-file",
        help="Write the CI markdown output to a file instead of stdout.",
    ),
) -> None:
    """
    Read an error log file and output a diagnosis and suggested fix.
    Use --ci to output raw Markdown for integration into CI pipelines.
    """
    if not os.path.exists(log_file):
        console.print(f"[bold red]Error:[/bold red] Log file '{log_file}' not found.")
        raise typer.Exit(code=1)

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        error_text, secrets_count1 = redact_secrets_with_count(f.read().strip())
        
    if not error_text:
        console.print("[bold red]Error:[/bold red] Log file is empty.")
        raise typer.Exit(code=1)

    config = load_config()
    if not provider:
        provider = config.get("default_provider", "ollama")
    if not category:
        category = config.get("default_category", "general")
    if not model:
        model = config.get("default_model", "llama3.1:8b")

    is_local = str(config.get("local_only", "")).lower() == "true" or config.get("local_only") is True
    if is_local and provider.lower() in ["groq", "gemini"]:
        if ci:
            print("**envfix encountered an error:** Local-only mode is enabled; cloud providers are disabled.")
        else:
            console.print("[bold red]Error:[/bold red] Local-only mode is enabled; cloud providers are disabled. Disable local-only mode to use cloud providers.")
        raise typer.Exit(code=1)

    code_context = extract_context(error_text)
    
    if not no_cache:
        cache_hit = find_cached_fix(error_text, category=category)
    else:
        cache_hit = None
        
    diagnosis_text = ""
    fix_text = ""
    source_tag = ""
    
    if cache_hit:
        diagnosis_text = cache_hit.diagnosis
        fix_text = _clean_fix(cache_hit.fix)
        source_tag = f" (from cache - {cache_hit.score:.0%} match)"
    else:
        try:
            display_model = get_actual_model(model, provider)
            if not ci:
                _print_ollama_warning_if_needed(provider, display_model)

            trimmed_error = trim_stack_trace(
                error_text,
                ignore_patterns=config.get("ignore_patterns", [])
            )
            result = get_diagnosis(
                stderr=trimmed_error,
                model=model,
                category=category,
                code_context=code_context,
                provider=provider,
            )
            diagnosis_text = result.diagnosis
            fix_text = result.fix
        except Exception as exc:
            if ci:
                print(f"**envfix encountered an error:** {exc}")
            else:
                if str(exc).startswith("[!]"):
                    console.print(f"[bold red]{exc}[/bold red]")
                else:
                    console.print(f"[bold red]Error reaching {provider}:[/bold red] {exc}")
            raise typer.Exit(code=1)
            
    if ci:
        # Extract a short error summary from the log (usually the last line for Python tracebacks)
        error_lines = [line.strip() for line in error_text.splitlines() if line.strip()]
        short_error = error_lines[-1][:200] if error_lines else "Unknown Error"
        
        if fix_text.strip() == "None (Code change required)":
            markdown_output = f"""## 🔧 envfix diagnosis{source_tag}
**Error detected:** {short_error}
**Diagnosis:** {diagnosis_text}

⚠️ *This appears to be a logic error in your code. Please manually edit the code as per the diagnosis.*"""
        else:
            markdown_output = f"""## 🔧 envfix diagnosis{source_tag}
**Error detected:** {short_error}
**Diagnosis:** {diagnosis_text}
**Suggested fix:**
```bash
{fix_text}
```"""
        if output_file:
            with open(output_file, "w", encoding="utf-8") as out_f:
                out_f.write(markdown_output)
        else:
            print(markdown_output)
    else:
        _show_fix_panel(diagnosis_text, fix_text, "cache" if cache_hit else provider, cache_hit.score if cache_hit else None)

    # In diagnose_cmd, we don't know if the fix worked because we don't apply it.
    error_lines = [line.strip() for line in error_text.splitlines() if line.strip()]
    error_type = "Unknown"
    if error_lines:
        last_line = error_lines[-1]
        if ":" in last_line:
            error_type = last_line.split(":")[0].split(" ")[-1]
        else:
            error_type = last_line[:50]

    send_telemetry(
        error_type=error_type,
        provider_used=provider or "unknown",
        was_cache_hit=(cache_hit is not None),
        fix_applied=False,
        fix_worked=None
    )

    raise typer.Exit(code=0)


@app.command()
def history(
    last: int = typer.Option(20, "--last", "-n", help="Show the last N attempts."),
) -> None:
    """
    Print a readable summary of past envfix attempts from the current user's log file.

    \b
        envfix history          # show last 20
        envfix history --last 5 # show last 5
    """
    entries = get_history()

    if not entries:
        console.print(
            "[yellow]No history found.[/yellow] "
            f"Run [bold]envfix run[/bold] on a failing command first.\n"
            f"(Looking for [dim]{get_log_file()}[/dim] in the current directory)"
        )
        return

    shown = entries[:last]
    total = len(entries)

    table = Table(
        title=f"envfix History  (showing {len(shown)} of {total} attempts)",
        border_style="cyan",
        show_lines=True,
        expand=False,
    )
    table.add_column("#",    no_wrap=True)
    table.add_column("When",        style="white",        width=16, no_wrap=True)
    table.add_column("Command",     style="bold white",   width=30)
    table.add_column("Fix",         style="cyan",         width=30)
    table.add_column("Category",    style="magenta",      width=10, no_wrap=True)
    table.add_column("Approved",    style="white",        width=8,  no_wrap=True)
    table.add_column("Worked",      style="white",        width=8,  no_wrap=True)
    table.add_column("Source",      style="dim",          width=7,  no_wrap=True)

    for idx, entry in enumerate(shown, start=1):
        # Format timestamp nicely
        ts = entry.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts)
            when = dt.strftime("%b %d  %H:%M")
        except (ValueError, TypeError):
            when = ts[:16]

        orig_cmd = entry.get("original_command", "-")
        fix_cmd  = entry.get("fix_command", "-")

        approved_val = entry.get("user_approved")
        worked_val   = entry.get("fix_worked")

        approved_str = "[green]y[/green]" if approved_val else "[red]n[/red]"

        if worked_val is True:
            worked_str = "[green][OK] yes[/green]"
        elif worked_val is False:
            worked_str = "[red][X] no[/red]"
        else:
            worked_str = "[dim]-[/dim]"

        source_str = entry.get("source", "ollama")
        cat_str = entry.get("category", "general")

        table.add_row(
            str(idx),
            when,
            orig_cmd,
            fix_cmd,
            cat_str,
            approved_str,
            worked_str,
            source_str,
        )

    console.print(table)
    console.print()


@app.command("stats")
def stats_cmd() -> None:
    """
    Print an aggregated summary of envfix usage statistics.
    """
    entries = get_history()
    
    if not entries:
        console.print("[yellow]No history found. Run [bold]envfix run[/bold] on a failing command first.[/yellow]")
        return
        
    total_diagnosed = len(entries)
    
    applied_fixes = [e for e in entries if e.get("fix_worked") is not None]
    if applied_fixes:
        successes = sum(1 for e in applied_fixes if e.get("fix_worked") is True)
        success_rate = (successes / len(applied_fixes)) * 100
    else:
        success_rate = 0.0
        
    # Calculate most used provider
    from collections import Counter
    providers = [e.get("provider", "ollama") for e in entries]
    most_used_provider = Counter(providers).most_common(1)[0][0] if providers else "None"
    
    # Calculate git stash creations from git reflog
    stash_count = 0
    try:
        import subprocess
        out = subprocess.check_output(
            ["git", "--no-pager", "reflog", "show", "refs/stash"], 
            stderr=subprocess.DEVNULL, 
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        for line in out.splitlines():
            if "envfix-auto-backup" in line:
                stash_count += 1
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Either not in a git repo, no stash reflog exists, or git not installed
        pass
        
    table = Table(title="envfix Statistics", border_style="cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="bold cyan")
    
    table.add_row("Total Errors Diagnosed", str(total_diagnosed))
    table.add_row("Success Rate", f"{success_rate:.1f}%")
    table.add_row("Most-Used Provider", most_used_provider)
    table.add_row("Safety Backups Created", str(stash_count))
    
    console.print(table)


def _detect_project_category(cwd: str) -> str:
    """Detect the project ecosystem based on telltale files."""
    if os.path.exists(os.path.join(cwd, "requirements.txt")) or os.path.exists(os.path.join(cwd, "pyproject.toml")):
        return "python"
    elif os.path.exists(os.path.join(cwd, "package.json")):
        return "node"
    elif os.path.exists(os.path.join(cwd, "Cargo.toml")):
        return "rust"
    elif os.path.exists(os.path.join(cwd, "go.mod")):
        return "go"
    elif os.path.exists(os.path.join(cwd, "pom.xml")) or os.path.exists(os.path.join(cwd, "build.gradle")):
        return "java"
    return "unknown"


@app.command("setup")
def setup_cmd() -> None:
    """Setup a working dev environment, including VS Code configuration."""
    import json
    cwd = os.getcwd()
    category = _detect_project_category(cwd)
    
    console.print(f"\n[bold cyan]envfix Setup[/bold cyan]")
    console.print(f"Detected project type: [bold]{category}[/bold]\n")
    
    actions_taken = []
    
    # 1. Python Venv creation
    if category == "python":
        venv_path = os.path.join(cwd, ".venv")
        if not os.path.exists(venv_path) and not os.path.exists(os.path.join(cwd, "venv")):
            if Confirm.ask("[bold]No virtual environment found. Create one (.venv)?[/bold]", default=True):
                console.print("[dim]Creating virtual environment...[/dim]")
                import subprocess
                res = subprocess.run(["python", "-m", "venv", ".venv"], capture_output=True)
                if res.returncode == 0:
                    actions_taken.append("Created Python virtual environment in .venv/")
                    if os.name == "nt":
                        activate_cmd = ".venv\\Scripts\\activate"
                    else:
                        activate_cmd = "source .venv/bin/activate"
                    actions_taken.append(f"To activate manually: {activate_cmd}")
                else:
                    console.print("[bold red]Failed to create virtual environment.[/bold red]")
        else:
            console.print("[dim]Virtual environment already exists.[/dim]")
            
    # 2. VS Code settings and extensions
    vscode_dir = os.path.join(cwd, ".vscode")
    os.makedirs(vscode_dir, exist_ok=True)
    
    # settings.json
    settings_path = os.path.join(vscode_dir, "settings.json")
    settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            settings = {}
            
    settings_modified = False
    if category == "python":
        if os.name == "nt":
            python_path = r"${workspaceFolder}\.venv\Scripts\python.exe"
        else:
            python_path = "${workspaceFolder}/.venv/bin/python"
            
        if settings.get("python.defaultInterpreterPath") != python_path:
            settings["python.defaultInterpreterPath"] = python_path
            settings_modified = True
            
    if settings_modified:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        actions_taken.append("Updated .vscode/settings.json with appropriate interpreter path")
        
    # extensions.json
    extensions_path = os.path.join(vscode_dir, "extensions.json")
    extensions = {}
    if os.path.exists(extensions_path):
        try:
            with open(extensions_path, "r", encoding="utf-8") as f:
                extensions = json.load(f)
        except Exception:
            extensions = {}
            
    recs = extensions.get("recommendations", [])
    ext_modified = False
    
    ext_map = {
        "python": "ms-python.python",
        "node": "dbaeumer.vscode-eslint",
        "rust": "rust-lang.rust-analyzer",
        "go": "golang.go",
        "java": "vscjava.vscode-java-pack"
    }
    
    recommended_ext = ext_map.get(category)
    if recommended_ext and recommended_ext not in recs:
        recs.append(recommended_ext)
        extensions["recommendations"] = recs
        ext_modified = True
        
    if ext_modified:
        with open(extensions_path, "w", encoding="utf-8") as f:
            json.dump(extensions, f, indent=4)
        actions_taken.append(f"Added {recommended_ext} to .vscode/extensions.json")
        
    if not actions_taken:
        console.print("[green]Environment is already set up. Nothing to do![/green]")
        return
        
    console.print("\n[bold green]Setup Summary:[/bold green]")
    step = 1
    for action in actions_taken:
        if action.startswith("To activate manually:"):
            console.print(f"   [dim]{action}[/dim]")
        else:
            console.print(f"{step}. {action}")
            step += 1
            
    if category == "python":
        console.print("\n[bold yellow]Next steps:[/bold yellow]")
        console.print("- Reload your VS Code window (Ctrl+Shift+P -> Developer: Reload Window) to pick up the new interpreter.")
        if any("activate" in a for a in actions_taken):
            console.print("- Activate your virtual environment in your terminal before running commands.")


@app.command("index")
def index_cmd(
    path: str = typer.Argument(
        ".",
        help="Directory to index (defaults to current directory)",
    ),
    update: bool = typer.Option(
        False,
        "--update",
        help="Only re-index changed files rather than rebuilding from scratch",
    ),
) -> None:
    """Build a local vector index of the codebase for context retrieval."""
    try:
        from envfix.indexer import build_index
    except ImportError as e:
        console.print(f"[bold red]Failed to load indexer module: {e}[/bold red]")
        raise typer.Exit(code=1)
        
    try:
        build_index(path=path, update=update)
    except Exception as e:
        console.print(f"[bold red]Indexing failed: {e}[/bold red]")
        raise typer.Exit(code=1)

@app.command("share")
def share_cmd(
    error_index: int = typer.Argument(0, help="The index of the error to share (0 is the most recent)."),
) -> None:
    """
    Generate a bug_report.md from a recent error to share with a mentor or teammate.
    """
    import platform
    import sys
    from datetime import datetime
    
    from envfix.logger import get_history
    from envfix.context import extract_context
    from envfix.redact import redact_secrets

    history = get_history()
    if not history:
        console.print("[yellow]No errors found in your envfix log.[/yellow]")
        raise typer.Exit(code=1)

    if error_index >= len(history) or error_index < 0:
        console.print(f"[red]Invalid index {error_index}. You only have {len(history)} recorded errors.[/red]")
        raise typer.Exit(code=1)

    entry = history[error_index]
    
    # Redact secrets
    error_text = redact_secrets(entry.get("error_text", ""))
    original_command = redact_secrets(entry.get("original_command", ""))
    diagnosis = entry.get("diagnosis", "")
    fix = entry.get("fix_command", "")
    timestamp = entry.get("timestamp", datetime.now().isoformat())
    
    code_context = extract_context(error_text)
    
    report = f"# Envfix Bug Report\n\n"
    report += f"**Timestamp:** {timestamp}\n"
    report += f"**OS:** {platform.system()} {platform.version()}\n"
    report += f"**Python Version:** {sys.version.split()[0]}\n\n"
    
    report += f"## Command\n```bash\n{original_command}\n```\n\n"
    report += f"## Error Output\n```text\n{error_text}\n```\n\n"
    
    if code_context:
        report += f"## Relevant Code (`{code_context.filepath}`, lines {code_context.start_line}-{code_context.end_line})\n"
        snippet = redact_secrets(code_context.snippet)
        report += f"```python\n{snippet}\n```\n\n"
        
    if diagnosis:
        report += f"## AI Diagnosis\n{diagnosis}\n\n"
        if fix and fix != "NONE":
            report += f"**Suggested Fix:**\n```bash\n{fix}\n```\n"
            report += f"**Did it work?:** {entry.get('fix_worked', 'Unknown')}\n\n"
            
    with open("bug_report.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    console.print(f"\n[green]Success! Bug report saved to bug_report.md - share this with a teammate or mentor.[/green]\n")


def _handle_internal_error(e: Exception) -> None:
    import traceback
    from pathlib import Path
    
    error_log = Path.home() / ".envfix" / "error.log"
    error_log.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(error_log, "a", encoding="utf-8") as f:
            f.write(f"\n--- Crash at {datetime.now(timezone.utc).isoformat()} ---\n")
            traceback.print_exc(file=f)
    except Exception:
        pass
        
    exc_name = type(e).__name__
    
    hints = {
        "UnicodeDecodeError": "This usually happens when a file is saved in an encoding other than UTF-8 (common on Windows with UTF-16 files).",
        "PermissionError": "This usually happens when envfix doesn't have the necessary file or network permissions.",
        "FileNotFoundError": "A file that envfix expected to read or write was not found.",
        "ConnectionError": "envfix had trouble connecting to a network resource or the local AI provider.",
        "JSONDecodeError": "envfix received an invalid or corrupted JSON response from an API or configuration file."
    }
    
    hint = hints.get(exc_name, "An unexpected internal error occurred.")
    
    from rich.console import Console
    console = Console()
    console.print(f"\n[bold red][!] envfix internal error[/bold red]")
    console.print(f"We hit an unexpected issue: [bold]{exc_name}[/bold]")
    console.print(f"{hint}\n")
    console.print("This is a bug in envfix itself, not your code. Consider running 'envfix share' to generate a report, or filing an issue at https://github.com/LOVEKUSH-rgb/deepproblemsolver/issues.\n")


def main() -> None:  # pragma: no cover
    from envfix.update import start_update_check, print_update_message_if_available
    import sys
    
    start_update_check()
    try:
        app()
    except SystemExit as e:
        print_update_message_if_available()
        sys.exit(e.code)
    except Exception as e:
        _handle_internal_error(e)
        print_update_message_if_available()
        sys.exit(1)
    else:
        print_update_message_if_available()


if __name__ == "__main__":  # pragma: no cover
    main()
