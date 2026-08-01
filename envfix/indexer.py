"""indexer.py — Local codebase context retrieval."""

import ast
import fnmatch
import json
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

try:
    import chromadb
except ImportError:
    chromadb = None  # type: ignore

from envfix.embeddings import get_embedding

INDEX_DIR = ".envfix_index"
MTIME_FILE = os.path.join(INDEX_DIR, "mtimes.json")
SAFELIST_EXTENSIONS = {
    ".py", ".js", ".ts", ".go", ".rs", ".java", ".md", ".txt",
    ".html", ".css", ".yml", ".yaml", ".toml", ".json", ".sh", ".bat", ".ps1"
}

HARDCODED_EXCLUDES = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    ".antigravity", ".vscode", ".idea", "dist", "build", "target"
}

SECRET_FILES_BLACKLIST = [
    ".env", ".env.local", ".env.*", "*.pem", "*.key", "*.pfx", 
    "credentials.json", "secrets.yaml", "secrets.yml", "id_rsa", "id_ed25519"
]


def _update_gitignore():
    """Ensure .envfix_index/ is in .gitignore."""
    gitignore_path = ".gitignore"
    entry = f"{INDEX_DIR}/"
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        if entry not in lines and INDEX_DIR not in lines:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write(f"\n# envfix local index\n{entry}\n")
    else:
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(f"# envfix local index\n{entry}\n")


def _get_files_to_index(base_path: str) -> tuple[List[str], int, int]:
    """Return all non-ignored codebase files, with a live count."""
    filtered = []
    skipped_large = 0
    skipped_sensitive = 0
    
    from rich.console import Console
    console = Console()

    def _is_allowed(filename: str, rel_dir: str = "") -> tuple[bool, str]:
        """Check if file matches extension and is not in hardcoded excludes or secrets."""
        if any(exc in rel_dir.split(os.sep) for exc in HARDCODED_EXCLUDES):
            return False, "excluded"
        
        # Secret file exclusion
        basename = os.path.basename(filename)
        for pattern in SECRET_FILES_BLACKLIST:
            if fnmatch.fnmatch(basename, pattern):
                return False, "sensitive"
                
        # Cloud credentials exclusion
        if basename == "credentials" and ".aws" in rel_dir.split(os.sep):
            return False, "sensitive"

        # Also check for hidden directories
        for part in rel_dir.split(os.sep):
            if part.startswith(".") and part != "." and part != INDEX_DIR:
                return False, "excluded"
                
        ext = os.path.splitext(filename)[1].lower()
        if ext in SAFELIST_EXTENSIONS:
            return True, "allowed"
        return False, "excluded"
    
    with console.status("[bold green]Scanning directory for files to index (0 found)...") as status:
        # Try git ls-files first
        try:
            process = subprocess.Popen(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=base_path
            )
            
            if process.stdout is not None:
                for line in process.stdout:
                    f = line.strip()
                    allowed, reason = _is_allowed(f, os.path.dirname(f))
                    if allowed:
                        full_path = str(Path(base_path) / f)
                        if os.path.isfile(full_path):
                            if os.path.getsize(full_path) > 1024 * 1024:
                                skipped_large += 1
                                continue
                            filtered.append(str(Path(full_path).resolve()))
                            if len(filtered) % 100 == 0:
                                status.update(f"[bold green]Scanning directory for files to index ({len(filtered):,} found)...")
                    elif reason == "sensitive":
                        skipped_sensitive += 1
                process.wait()
                if process.returncode == 0:
                    return filtered, skipped_large, skipped_sensitive
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass

        # Fallback to os.walk if git fails
        filtered = []
        for root, dirs, files in os.walk(base_path):
            # Prune excluded directories
            dirs[:] = [
                d for d in dirs
                if d not in HARDCODED_EXCLUDES 
                and d != INDEX_DIR
                and not (d.startswith(".") and d != ".")
            ]
            
            rel_root = os.path.relpath(root, base_path)
            for file in files:
                allowed, reason = _is_allowed(file, rel_root)
                if allowed:
                    full_path = str(Path(root) / file)
                    if os.path.isfile(full_path):
                        if os.path.getsize(full_path) > 1024 * 1024:
                            skipped_large += 1
                            continue
                        filtered.append(str(Path(full_path).resolve()))
                        if len(filtered) % 100 == 0:
                            status.update(f"[bold green]Scanning directory for files to index ({len(filtered):,} found)...")
                elif reason == "sensitive":
                    skipped_sensitive += 1
                        
    return filtered, skipped_large, skipped_sensitive


def chunk_python_file(filepath: str, text: str) -> List[Dict[str, Any]]:
    """Chunk Python code using AST to keep classes and functions intact."""
    chunks = []
    try:
        tree = ast.parse(text, filename=filepath)
        
        # If the file is very small or has no classes/functions, just return it as one chunk
        if len(text.splitlines()) < 50:
            return [{"filepath": filepath, "start": 1, "end": len(text.splitlines()), "text": text}]
            
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # extract segment
                segment = ast.get_source_segment(text, node)
                if segment:
                    chunks.append({
                        "filepath": filepath,
                        "start": node.lineno,
                        "end": node.end_lineno or node.lineno,
                        "text": segment
                    })
            else:
                # Top-level statements that are not functions or classes (e.g. imports)
                pass
                
        # If no functions or classes were found, fallback
        if not chunks:
            return chunk_generic_file(filepath, text)
            
        return chunks
    except SyntaxError:
        # Fallback to generic chunking if syntax is invalid
        return chunk_generic_file(filepath, text)


def chunk_generic_file(filepath: str, text: str, window: int = 50, overlap: int = 10) -> List[Dict[str, Any]]:
    """Chunk non-Python files using a sliding line window."""
    lines = text.splitlines()
    chunks = []
    if not lines:
        return chunks
        
    start = 0
    while start < len(lines):
        end = min(start + window, len(lines))
        chunk_lines = lines[start:end]
        chunks.append({
            "filepath": filepath,
            "start": start + 1,
            "end": end,
            "text": "\n".join(chunk_lines)
        })
        if end == len(lines):
            break
        start += (window - overlap)
        
    return chunks


def build_index(path: str = ".", update: bool = False, client_instance=None) -> None:
    """Scan and index the codebase."""
    if chromadb is None:
        raise RuntimeError(
            "chromadb is not installed. Please run: pip install chromadb"
        )
        
    if get_embedding("test") is None:
        raise RuntimeError(
            "sentence-transformers is not installed. Required for codebase indexing. "
            "Run: pip install envfix[semantic] or pip install sentence-transformers"
        )

    # Use absolute path for index storage so it's placed in the targeted project dir
    abs_path = str(Path(path).resolve())
    index_dir_path = str(Path(abs_path) / INDEX_DIR)
    mtime_file_path = str(Path(abs_path) / MTIME_FILE)

    _update_gitignore()
    
    files, skipped_large, skipped_sensitive = _get_files_to_index(abs_path)
    
    if len(files) > 5000:
        import typer
        from rich.console import Console
        from rich.prompt import Confirm
        console = Console()
        console.print(
            f"\n[bold yellow]WARNING: This directory contains {len(files):,} files[/bold yellow] - that's unusually "
            "large for a single project and may mean you're indexing the "
            "wrong directory (e.g. your home folder instead of a project folder)."
        )
        console.print(f"\nCurrent directory: {abs_path}\n")
        
        if not Confirm.ask("Continue anyway? (Or run 'envfix index <path>' to target a specific project folder instead)"):
            raise typer.Exit(code=1)
    
    # Load mtimes
    mtimes: Dict[str, float] = {}
    if update and os.path.exists(mtime_file_path):
        try:
            with open(mtime_file_path, "r", encoding="utf-8") as f:
                mtimes = json.load(f)
        except json.JSONDecodeError:
            pass

    client = client_instance or chromadb.PersistentClient(path=index_dir_path)
    collection = client.get_or_create_collection("codebase")
    
    files_to_index = []
    
    for f in files:
        mtime = os.path.getmtime(f)
        if update and f in mtimes and mtimes[f] >= mtime:
            continue
        files_to_index.append((f, mtime))
        
    if not files_to_index:
        print("Index is up-to-date. No changed files found.")
        return
        
    print(f"Indexing {len(files_to_index)} files...")

    # For 'update', we should delete old chunks of these files
    if update:
        for f, _ in files_to_index:
            try:
                collection.delete(where={"filepath": f})
            except Exception:
                pass
                
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Chunking and Embedding...", total=len(files_to_index))
        
        for f, mtime in files_to_index:
            progress.update(task, description=f"Processing {f[:30]}...")
            try:
                with open(f, "r", encoding="utf-8") as file_obj:
                    text = file_obj.read()
            except UnicodeDecodeError:
                progress.advance(task)
                continue
                
            if f.endswith(".py"):
                chunks = chunk_python_file(f, text)
            else:
                chunks = chunk_generic_file(f, text)
                
            if not chunks:
                progress.advance(task)
                continue
                
            ids = []
            embeddings = []
            metadatas = []
            documents = []
            
            for i, chunk in enumerate(chunks):
                chunk_id = f"{f}_chunk_{i}"
                chunk_text = chunk["text"].strip()
                if not chunk_text:
                    continue
                    
                emb = get_embedding(chunk_text)
                if emb is None:
                    continue
                    
                ids.append(chunk_id)
                embeddings.append(emb)
                metadatas.append({
                    "filepath": f,
                    "start": chunk["start"],
                    "end": chunk["end"]
                })
                documents.append(chunk_text)
                
            if ids:
                # Add in batches if necessary, but files usually don't have thousands of chunks
                collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas, # type: ignore
                    documents=documents
                )
                
            mtimes[f] = mtime
            progress.advance(task)
            
            # Save mtimes
    os.makedirs(index_dir_path, exist_ok=True)
    with open(mtime_file_path, "w", encoding="utf-8") as f:
        json.dump(mtimes, f)
        
    summary_parts = [f"Successfully indexed {len(files_to_index)} files"]
    if skipped_large > 0:
        summary_parts.append(f"skipped {skipped_large} large files")
    if skipped_sensitive > 0:
        summary_parts.append(f"skipped {skipped_sensitive} sensitive files")
        
    print(f"\n{', '.join(summary_parts)}.")


def query_index(query_text: str, top_k: int = 3, threshold: float = 1.2) -> List[str]:
    """
    Query the local index for relevant chunks.
    Returns a list of redacted code chunks.
    """
    if chromadb is None or not os.path.exists(INDEX_DIR):
        return []
        
    emb = get_embedding(query_text)
    if emb is None:
        return []
        
    try:
        client = chromadb.PersistentClient(path=INDEX_DIR)
        collection = client.get_collection("codebase")
    except Exception:
        return []
        
    results = collection.query(
        query_embeddings=[emb],
        n_results=top_k
    )
    
    if not results or not results["documents"] or not results["documents"][0]:
        return []
        
    chunks = []
    distances = results["distances"][0] if "distances" in results and results["distances"] else [0] * len(results["documents"][0]) # type: ignore
    
    from envfix.redact import redact_secrets
    
    for i, doc in enumerate(results["documents"][0]):
        dist = distances[i]
        if dist <= threshold:
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            filepath = meta.get("filepath", "unknown")
            start = meta.get("start", "?")
            end = meta.get("end", "?")
            
            header = f"--- {filepath} (lines {start}-{end}) ---"
            redacted_doc = redact_secrets(doc)
            chunks.append(f"{header}\n{redacted_doc}")
            
    return chunks
