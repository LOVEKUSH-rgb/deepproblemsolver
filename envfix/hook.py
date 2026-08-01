import os
import stat
import subprocess
import ast
import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.prompt import Confirm

console = Console()
hook_app = typer.Typer(name="hook", help="Manage git pre-commit hooks.")

HOOK_SCRIPT = """#!/bin/sh
envfix hook-check
"""

@hook_app.command("install")
def install() -> None:
    """Install the envfix pre-commit hook in the current git repository."""
    try:
        git_dir = subprocess.check_output(["git", "rev-parse", "--git-dir"], text=True).strip()
    except subprocess.CalledProcessError:
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(1)
        
    hook_path = Path(git_dir) / "hooks" / "pre-commit"
    
    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8")
        if "envfix hook-check" in content:
            console.print("[green]The envfix pre-commit hook is already installed.[/green]")
            return
            
        console.print(f"[yellow]A pre-commit hook already exists at {hook_path}[/yellow]")
        if Confirm.ask("Do you want to append the envfix hook to it?"):
            with open(hook_path, "a", encoding="utf-8") as f:
                f.write("\n" + HOOK_SCRIPT)
            console.print("[green]Appended envfix to existing pre-commit hook.[/green]")
        else:
            console.print("Installation aborted.")
            return
    else:
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        with open(hook_path, "w", encoding="utf-8", newline='\n') as f:
            f.write(HOOK_SCRIPT)
        console.print(f"[green]Installed envfix pre-commit hook at {hook_path}[/green]")
        
    # Make executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)


@hook_app.command("uninstall")
def uninstall() -> None:
    """Uninstall the envfix pre-commit hook from the current git repository."""
    try:
        git_dir = subprocess.check_output(["git", "rev-parse", "--git-dir"], text=True).strip()
    except subprocess.CalledProcessError:
        console.print("[red]Not inside a git repository.[/red]")
        raise typer.Exit(1)
        
    hook_path = Path(git_dir) / "hooks" / "pre-commit"
    if not hook_path.exists():
        console.print("[yellow]No pre-commit hook found.[/yellow]")
        return
        
    content = hook_path.read_text(encoding="utf-8")
    if "envfix hook-check" not in content:
        console.print("[yellow]envfix is not installed in the pre-commit hook.[/yellow]")
        return
        
    if content.strip() == HOOK_SCRIPT.strip():
        # Only envfix is here, remove the file
        hook_path.unlink()
        console.print("[green]Removed envfix pre-commit hook entirely.[/green]")
    else:
        # Other stuff is here, remove only our lines
        new_lines = [line for line in content.splitlines() if line.strip() != "envfix hook-check" and line.strip() != ""]
        with open(hook_path, "w", encoding="utf-8", newline='\n') as f:
            f.write("\n".join(new_lines) + "\n")
        console.print("[green]Removed envfix from existing pre-commit hook.[/green]")


def run_hook_check() -> None:
    """Internal fast syntax checker run by the pre-commit hook."""
    try:
        output = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], text=True)
    except subprocess.CalledProcessError:
        sys.exit(0)
        
    files = [f.strip() for f in output.splitlines() if f.strip()]
    has_errors = False
    
    for file_str in files:
        filepath = Path(file_str)
        if not filepath.exists() or filepath.suffix not in {".py", ".js", ".ts"}:
            continue
            
        if filepath.suffix != ".py":
            # Fast syntax checking for JS/TS is not yet implemented locally
            continue
            
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            ast.parse(content, filename=str(filepath))
        except UnicodeDecodeError:
            # Skip files that cannot be decoded as UTF-8 (e.g., binary files misnamed as .py)
            continue
        except SyntaxError as e:
            has_errors = True
            console.print(f"[red]Syntax error in staged file:[/red] {filepath}")
            console.print(f"  Line {e.lineno}: {e.msg}")
            
    if has_errors:
        console.print("[red]Commit rejected. Please fix the syntax errors above.[/red]")
        sys.exit(1)
