"""main.py — Typer CLI entry point for envfix (Phase 2)."""

import os
import sys
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

app = typer.Typer(
    name="envfix",
    help="Diagnose and auto-fix Python/ML environment errors using a local LLM.",
    add_completion=False,
)

console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    })
    
    console.print("\n[bold green]Configuration saved successfully![/bold green]")


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

    # ── Step 1: Run the original command ─────────────────────────────────
    console.print(f"\n[bold cyan]▶ Running:[/bold cyan] {cmd}\n")
    stdout, stderr, returncode = run_command(cmd)

    if stdout:
        console.print(stdout, end="")

    if returncode == 0:
        console.print("\n[bold green]✓ Command succeeded — nothing to fix![/bold green]")
        return

    # ── Step 2: Command failed — show the error ───────────────────────────
    error_text = stderr.strip() or stdout.strip() or "(no output captured)"
    console.print(
        Panel(
            error_text,
            title="[bold red]✗ Command Failed[/bold red]",
            border_style="red",
            expand=False,
        )
    )

    # ── Step 3: Extract code context from the stack trace ─────────────────
    code_context = extract_context(error_text)
    if code_context:
        console.print(
            f"[dim]📎 Context found: {code_context.filepath} "
            f"(lines {code_context.start_line}–{code_context.end_line})[/dim]"
        )

    # ── Step 4: Check known-fix cache before calling the model ───────────
    if not no_cache:
        cache_hit = find_cached_fix(error_text, category=category)
    else:
        cache_hit = None
    
    source = provider

    if cache_hit:
        if cache_hit.previously_worked:
            banner = (
                f"⚡ Found a previously [bold green]verified[/bold green] fix "
                f"for a similar error ({cache_hit.score:.0%} match) — skipping model call."
            )
        else:
            banner = (
                f"⚡ Found a previously [bold yellow]attempted[/bold yellow] fix "
                f"for a similar error ({cache_hit.score:.0%} match) — "
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
        # ── Step 4a: Ask the LLM ─────────────────────────────────────────
        provider_name = provider.capitalize()
        display_model = get_actual_model(model, provider)
        console.print(
            f"\n[bold yellow]🤖 Asking {provider_name} ({display_model}) for a diagnosis…[/bold yellow]"
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
            console.print(f"\n[bold red]Error reaching {provider_name}:[/bold red] {exc}")
            raise typer.Exit(code=1)

        if not result.parsed_ok:
            console.print(
                "\n[bold yellow]⚠ Could not parse a structured response. "
                "Showing raw model output:[/bold yellow]"
            )
            console.print(
                Panel(result.raw_response, border_style="yellow", expand=False)
            )
            log_attempt(
                original_command=cmd,
                error_text=error_text,
                diagnosis=result.diagnosis,
                fix_command=result.fix,
                user_approved=False,
                fix_worked=None,
                source=provider,
                category=category,
                context_included=code_context is not None,
                provider=provider,
            )
            raise typer.Exit(code=1)

        diagnosis = result.diagnosis
        fix = result.fix
        _show_fix_panel(diagnosis, fix, source)

    # ── Step 4b: Dry-run preview ──────────────────────────────────────────
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
            original_command=cmd,
            error_text=error_text,
            diagnosis=diagnosis,
            fix_command=fix,
            user_approved=False,
            fix_worked=None,
            source=source,
            category=category,
            context_included=code_context is not None,
            provider=provider,
        )
        raise typer.Exit(code=0)

    # ── Git Safety Backup ──────────────────────────────────────────────────
    stash_created = False
    if not is_in_git_repo():
        console.print(
            "[bold yellow]Warning: not in a git repository. envfix cannot create "
            "a safety backup before applying fixes. Consider running 'git init' "
            "for safety.[/bold yellow]\n"
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
            "[bold red]✗ Fix command itself failed "
            f"(exit code {fix_rc}). Aborting retry.[/bold red]"
        )
        log_attempt(
            original_command=cmd,
            error_text=error_text,
            diagnosis=diagnosis,
            fix_command=fix,
            user_approved=True,
            fix_worked=False,
            source=source,
            category=category,
            context_included=code_context is not None,
            provider=provider,
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
            console.print(f"\n[bold magenta]⚙ Running post-fix hook:[/bold magenta] {hook}")
            hook_stdout, hook_stderr, _ = run_command(hook)
            if hook_stdout:
                console.print(hook_stdout, end="")
            if hook_stderr:
                console.print(hook_stderr, end="")
    else:
        console.print(
            "\n[bold red]✗ Original command still failed after the fix "
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
        original_command=cmd,
        error_text=error_text,
        diagnosis=diagnosis,
        fix_command=fix,
        user_approved=True,
        fix_worked=worked,
        source=source,
        category=category,
        context_included=code_context is not None,
        provider=provider,
    )
    console.print(f"\n[dim]📝 Attempt logged to {get_log_file()}[/dim]")
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
) -> None:
    """
    Read an error log file and output a diagnosis and suggested fix.
    Use --ci to output raw Markdown for integration into CI pipelines.
    """
    if not os.path.exists(log_file):
        console.print(f"[bold red]Error:[/bold red] Log file '{log_file}' not found.")
        raise typer.Exit(code=1)

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        error_text = f.read().strip()
        
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
        source_tag = f" (from cache — {cache_hit.score:.0%} match)"
    else:
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
            diagnosis_text = result.diagnosis
            fix_text = result.fix
        except Exception as exc:
            if ci:
                print(f"**envfix encountered an error:** {exc}")
            else:
                console.print(f"[bold red]Error reaching {provider}:[/bold red] {exc}")
            raise typer.Exit(code=1)
            
    if ci:
        # Output pure Markdown to standard out for CI capture
        markdown_output = f"""### 🛠️ envfix Suggestion{source_tag}

#### Diagnosis
{diagnosis_text}

#### Proposed Fix
```bash
{fix_text}
```
"""
        print(markdown_output)
    else:
        _show_fix_panel(diagnosis_text, fix_text, "cache" if cache_hit else provider, cache_hit.score if cache_hit else None)
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

        orig_cmd = entry.get("original_command", "—")
        fix_cmd  = entry.get("fix_command", "—")

        approved_val = entry.get("user_approved")
        worked_val   = entry.get("fix_worked")

        approved_str = "[green]y[/green]" if approved_val else "[red]n[/red]"

        if worked_val is True:
            worked_str = "[green]✓ yes[/green]"
        elif worked_val is False:
            worked_str = "[red]✗ no[/red]"
        else:
            worked_str = "[dim]—[/dim]"

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

    console.print()
    console.print(table)
    console.print()


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
