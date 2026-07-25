"""main.py — Typer CLI entry point for envfix."""

import sys
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from envfix.ai import get_diagnosis
from envfix.logger import log_attempt
from envfix.runner import run_command

app = typer.Typer(
    name="envfix",
    help="Diagnose and auto-fix Python/ML environment errors using a local LLM.",
    add_completion=False,
)
console = Console()


@app.command(
    # ignore_unknown_options + allow_extra_args means flags like -m, -c, --gpu
    # inside the user's shell command are NEVER consumed by Typer's own parser.
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def run(
    ctx: typer.Context,
    model: str = typer.Option(
        "llama3.1:8b",
        "--model",           # only --model works; -m is intentionally removed
        help="Ollama model tag to use for diagnosis.",
        show_default=True,
    ),
) -> None:
    """
    Run COMMAND. If it fails, diagnose the error with a local LLM,
    propose a fix, and (with your approval) apply it and retry.

    Everything after [OPTIONS] is treated as the command to run:

    \b
        envfix run python -m pip install torch
        envfix run "python -c 'import torch'"
        envfix run python train.py --gpu 0
        envfix run --model qwen2.5:3b python train.py
    """
    # ctx.args holds tokens Typer did NOT consume as its own option.
    # Typer 0.27 bug: with allow_extra_args=True the subcommand name ("run")
    # leaks as ctx.args[0]. Strip it so we don't execute "run python -m ..."
    args = list(ctx.args)
    if args and args[0] == "run":
        args.pop(0)
    cmd = " ".join(args)

    if not cmd.strip():
        console.print(
            "[bold red]Error:[/bold red] No command provided.\n"
            "Usage:  [bold]envfix run[/bold] [OPTIONS] COMMAND...\n"
            "Example:[bold] envfix run python -m pip install torch[/bold]"
        )
        raise typer.Exit(code=1)

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

    # ── Step 3: Ask the LLM for a diagnosis ──────────────────────────────
    console.print(
        f"\n[bold yellow]🤖 Asking Ollama ({model}) for a diagnosis…[/bold yellow]"
    )
    try:
        result = get_diagnosis(stderr=error_text, model=model)
    except RuntimeError as exc:
        console.print(f"\n[bold red]Error reaching Ollama:[/bold red] {exc}")
        raise typer.Exit(code=1)

    # ── Step 4: Display diagnosis + fix ──────────────────────────────────
    if not result.parsed_ok:
        console.print(
            "\n[bold yellow]⚠ Could not parse a structured response. "
            "Showing raw model output:[/bold yellow]"
        )
        console.print(Panel(result.raw_response, border_style="yellow", expand=False))
        log_attempt(
            command=cmd,
            stderr=error_text,
            diagnosis=result.diagnosis,
            fix=result.fix,
            approved=False,
            worked=None,
        )
        raise typer.Exit(code=1)

    console.print(
        Panel(
            Text.assemble(
                ("DIAGNOSIS\n", "bold magenta"),
                (result.diagnosis + "\n\n", "white"),
                ("FIX\n", "bold cyan"),
                (result.fix, "bold white"),
            ),
            title="[bold]envfix Suggestion[/bold]",
            border_style="cyan",
            expand=False,
        )
    )

    # ── Step 5: Ask for approval ──────────────────────────────────────────
    approved = Confirm.ask("\n[bold]Run this fix?[/bold]", default=False)

    if not approved:
        console.print("[dim]Exiting without changes.[/dim]")
        log_attempt(
            command=cmd,
            stderr=error_text,
            diagnosis=result.diagnosis,
            fix=result.fix,
            approved=False,
            worked=None,
        )
        raise typer.Exit(code=0)

    # ── Step 6: Run the fix, then re-run the original command ─────────────
    console.print(f"\n[bold cyan]⚙ Applying fix:[/bold cyan] {result.fix}\n")
    fix_stdout, fix_stderr, fix_rc = run_command(result.fix)

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
            command=cmd,
            stderr=error_text,
            diagnosis=result.diagnosis,
            fix=result.fix,
            approved=True,
            worked=False,
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
    else:
        console.print(
            "\n[bold red]✗ Original command still failed after the fix "
            f"(exit code {retry_rc}). "
            "You may need to try a different approach.[/bold red]"
        )

    # ── Step 8: Log everything ────────────────────────────────────────────
    log_attempt(
        command=cmd,
        stderr=error_text,
        diagnosis=result.diagnosis,
        fix=result.fix,
        approved=True,
        worked=worked,
    )
    console.print(
        f"\n[dim]📝 Attempt logged to envfix_log.json[/dim]"
    )
    raise typer.Exit(code=0 if worked else 1)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
