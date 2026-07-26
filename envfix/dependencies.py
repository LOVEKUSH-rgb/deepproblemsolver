"""dependencies.py — Auto-append fixed packages to requirements files."""

import os
import re


def extract_package_name(fix_command: str) -> str | None:
    """
    Extract the package name from a pip install command.
    Example: 'python -m pip install -U torch' -> 'torch'
    """
    # Matches 'pip install', optional flags like '-U' or '--upgrade',
    # and then captures the package name.
    # Note: this is a heuristic and will grab the first package if multiple are specified.
    match = re.search(r"pip\s+install\s+(?:-[a-zA-Z-]+\s+)*([a-zA-Z0-9_.-]+)", fix_command, re.IGNORECASE)
    if match:
        pkg = match.group(1).strip()
        # Ignore common flags that might have been caught if regex missed them
        if not pkg.startswith("-") and not pkg.endswith(".txt"):
            return pkg
    return None


def update_requirements_txt(path: str, package: str) -> None:
    """Append the package to requirements.txt, ensuring a trailing newline."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Avoid adding if it's already there
    if re.search(rf"^{re.escape(package)}(?:[<>=!].*)?$", content, re.MULTILINE | re.IGNORECASE):
        return

    with open(path, "a", encoding="utf-8") as f:
        if content and not content.endswith("\n"):
            f.write("\n")
        f.write(f"{package}\n")


def update_pyproject_toml(path: str, package: str) -> None:
    """
    Insert the package into the [project] dependencies array in pyproject.toml.
    Uses string manipulation to preserve comments and formatting.
    """
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Avoid adding if it's already there (rudimentary check)
    if f'"{package}"' in content or f"'{package}'" in content:
        return

    project_start = content.find("[project]")
    if project_start == -1:
        return

    next_section = content.find("\n[", project_start + 1)
    if next_section == -1:
        next_section = len(content)

    project_block = content[project_start:next_section]

    # Find the dependencies array
    match = re.search(r"(dependencies\s*=\s*\[)(.*?)(\])", project_block, flags=re.DOTALL)
    if not match:
        return

    inner = match.group(2)
    if "\n" in inner:
        # Multi-line array: insert at the top to avoid trailing comma issues at the bottom
        new_project_block = re.sub(
            r"(dependencies\s*=\s*\[\s*\n)",
            rf'\g<1>    "{package}",\n',
            project_block,
            count=1
        )
    else:
        # Single-line array
        inner_stripped = inner.strip()
        if inner_stripped:
            # Add at the beginning of the single line
            new_inner = f'"{package}", ' + inner_stripped
        else:
            new_inner = f'"{package}"'
            
        new_project_block = re.sub(
            r"(dependencies\s*=\s*\[).*?(\])",
            rf'\g<1>{new_inner}\g<2>',
            project_block,
            count=1,
            flags=re.DOTALL
        )

    # Reconstruct the file
    new_content = content[:project_start] + new_project_block + content[next_section:]
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
