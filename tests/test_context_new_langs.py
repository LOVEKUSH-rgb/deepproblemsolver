import os
from pathlib import Path
from unittest import mock
from envfix.context import extract_context, trim_stack_trace

def test_extract_context_rust():
    stderr = """
error[E0425]: cannot find value `x` in this scope
 --> src/main.rs:4:5
  |
4 |     let y = x;
  |             ^ not found in this scope
"""
    with mock.patch("envfix.context.Path.is_file", return_value=True):
        with mock.patch("envfix.context.Path.read_text", return_value="fn main() {\n\n\n    let y = x;\n}"):
            ctx = extract_context(stderr, cwd="/dummy")
            assert ctx is not None
            assert "src/main.rs" in ctx.filepath.replace("\\", "/")
            assert ctx.line_number == 4

def test_extract_context_go():
    stderr = """
# command-line-arguments
./main.go:5:2: undefined: fmt
"""
    with mock.patch("envfix.context.Path.is_file", return_value=True):
        with mock.patch("envfix.context.Path.read_text", return_value="package main\n\nfunc main() {\n\n\tfmt.Println()\n}"):
            ctx = extract_context(stderr, cwd="/dummy")
            assert ctx is not None
            assert ctx.filepath == "main.go"
            assert ctx.line_number == 5

def test_extract_context_java_compiler():
    stderr = """
[ERROR] COMPILATION ERROR : 
[ERROR] /path/to/project/src/main/java/Main.java:[10,5] cannot find symbol
"""
    # mock relative_to to just return 'src/main/java/Main.java'
    with mock.patch("envfix.context.Path.is_file", return_value=True):
        with mock.patch("envfix.context.Path.read_text", return_value="\n"*9 + "    System.out.println(x);\n"):
            ctx = extract_context(stderr, cwd="/path/to/project")
            assert ctx is not None
            assert ctx.line_number == 10
            assert "Main.java" in ctx.filepath

def test_extract_context_docker():
    stderr = """
failed to solve with frontend dockerfile.v0: line 10: unknown instruction: RUNN
"""
    with mock.patch("envfix.context.Path.is_file", return_value=True):
        with mock.patch("envfix.context.Path.read_text", return_value="\n"*9 + "RUNN echo hello\n"):
            ctx = extract_context(stderr, cwd="/dummy")
            assert ctx is not None
            assert ctx.line_number == 10
            assert "dockerfile" in ctx.filepath.lower()

def test_trim_stack_trace_hides_go_mod():
    stderr = """
panic: runtime error
goroutine 1 [running]:
main.main()
	/path/to/project/main.go:5:2
some/pkg.func()
	/path/to/go/pkg/mod/some/pkg@v1.0.0/file.go:10:1
"""
    # /path/to/go/pkg/mod/... should be hidden because of "go/pkg/mod" in external_markers
    trimmed = trim_stack_trace(stderr, cwd="/path/to/project")
    assert "/path/to/project/main.go" in trimmed
    assert "external frames hidden" in trimmed
    assert "file.go:10:1" not in trimmed

def test_trim_stack_trace_hides_cargo_registry():
    stderr = """
thread 'main' panicked at 'explicit panic', src/main.rs:4:5
stack backtrace:
   0: std::panicking::begin_panic
             at /rustc/hash/library/std/src/panicking.rs:645:5
   1: core::panicking::panic_fmt
             at /rustc/hash/library/core/src/panicking.rs:72:14
   2: my_crate::main
             at --> src/main.rs:4:5
   3: some_dep::func
             at --> /home/user/.cargo/registry/src/github.com-1ecc6299db9ec823/some_dep-1.0/src/lib.rs:10:1
"""
    trimmed = trim_stack_trace(stderr, cwd="/path/to/project")
    assert "src/main.rs:4:5" in trimmed
    assert "external frames hidden" in trimmed
    assert "some_dep-1.0/src/lib.rs" not in trimmed
