import pytest

from acco.output_processors import (
    ProcessorRegistry,
    explain_processor,
    process_output,
)


def test_pytest_failure_uses_failure_aware_processor_and_preserves_assertion():
    chatter = "\n".join(f"collecting {i}" for i in range(150))
    text = (
        chatter
        + "\n============================= FAILURES =============================\n"
        + "____________________________ test_refresh ____________________________\n"
        + "E   AssertionError: expected 200, got 401\n"
        + "=========================== short test summary info ===========================\n"
        + "FAILED tests/test_auth.py::test_refresh - AssertionError: expected 200, got 401\n"
        + "======================= 1 failed, 40 passed in 1.2s =======================\n"
    )
    result = process_output(text, "pytest -q", exit_code=1, min_reduction=0.0)
    assert result.processor == "pytest"
    assert result.failed is True
    assert result.compressed is True
    assert "AssertionError: expected 200, got 401" in result.text
    assert result.text.count("collecting") < 10


def test_failed_install_skips_success_only_processor():
    text = ("npm ERR! could not resolve dependency\n" * 80) + "fatal detail\n"
    result = process_output(
        text, "npm install", exit_code=1, min_reduction=0.0,
    )
    assert result.processor == "generic"
    assert result.text == text
    info = explain_processor("npm install", exit_code=1)
    assert info["processor"] == "generic"
    assert "package-install" in info["failure_skipped_processors"]


def test_critical_line_recovery_is_registry_wide():
    class Lossy:
        name = "lossy"
        priority = 1
        handles_failure = True

        def matches(self, command):
            return True

        def compress(self, command, text, *, failed, max_lines, keep_tail):
            return "short summary\n"

    class Generic:
        name = "generic"
        priority = 999
        handles_failure = True

        def matches(self, command):
            return True

        def compress(self, command, text, *, failed, max_lines, keep_tail):
            return text

    original = (
        "noise\n" * 200
        + "src/auth.py:42: AssertionError: refresh token expired\n"
        + "more noise\n" * 100
    )
    result = process_output(
        original,
        "custom check",
        exit_code=1,
        min_reduction=0.0,
        registry=ProcessorRegistry([Lossy(), Generic()]),
    )
    assert result.processor == "lossy"
    assert "src/auth.py:42: AssertionError: refresh token expired" in result.text
    assert result.recovered_lines


def test_ratio_gate_rejects_marginal_compression():
    class TinyTrim:
        name = "tiny"
        priority = 1
        handles_failure = True

        def matches(self, command):
            return True

        def compress(self, command, text, *, failed, max_lines, keep_tail):
            return text[:-1]

    class Generic(TinyTrim):
        name = "generic"
        priority = 999

    text = "x" * 1000
    result = process_output(
        text,
        "anything",
        min_reduction=0.02,
        registry=ProcessorRegistry([TinyTrim(), Generic()]),
    )
    assert result.text == text
    assert result.compressed is False



def test_search_processor_keeps_bounded_unique_hits():
    """Large grep output should keep unique early hits and report omissions."""
    text = "\n".join(
        [f"src/file_{index}.py:10:match" for index in range(120)]
        + ["src/file_0.py:10:match"] * 40
    )
    result = process_output(
        text,
        "rg match src",
        exit_code=0,
        min_reduction=0.0,
    )
    assert result.processor == "search"
    assert result.compressed is True
    assert "src/file_0.py:10:match" in result.text
    assert "omitted" in result.text


@pytest.mark.parametrize(
    "command",
    [
        'grep -n "_get_aligned_offsets\\|class HPacker" -A 40 lib/offsetbox.py | head -200',
        "grep -rnA5 needle src",
        "rg -C3 needle src",
        "rg --context 3 needle src",
        "grep --after-context=4 needle src/app.py",
    ],
)
def test_search_processor_keeps_context_searches_whole(command):
    """-A/-B/-C output is code the agent asked to read; never cap it to hits."""
    text = "\n".join(f"{130 + index}-    body line {index}" for index in range(143))
    result = process_output(text, command, exit_code=0, min_reduction=0.0)
    assert result.processor == "search"
    assert result.compressed is False
    assert result.text.rstrip("\n") == text


def test_lint_processor_preserves_failure_locations():
    """Ruff/ESLint compression should preserve file and rule evidence."""
    chatter = "\n".join(f"checking {index}" for index in range(150))
    text = (
        chatter
        + "\nsrc/app.py:42:5: F821 Undefined name 'user'\n"
        + "Found 1 error.\n"
    )
    result = process_output(
        text,
        "ruff check .",
        exit_code=1,
        min_reduction=0.0,
    )
    assert result.processor == "ruff"
    assert result.failed is True
    assert "src/app.py:42:5" in result.text
    assert "F821" in result.text


def test_typecheck_processor_preserves_ts_diagnostics():
    """TypeScript diagnostics should survive typecheck compression."""
    text = (
        "\n".join(f"building module {index}" for index in range(150))
        + "\nsrc/app.ts(10,4): error TS2322: Type 'string' is not assignable\n"
        + "Found 1 error.\n"
    )
    result = process_output(
        text,
        "npx tsc --noEmit",
        exit_code=2,
        min_reduction=0.0,
    )
    assert result.processor == "tsc"
    assert "TS2322" in result.text


def test_compiled_test_processor_preserves_go_failure_summary():
    """Go test output should retain failing test and package summary."""
    text = (
        "\n".join(f"=== RUN TestNoise{index}" for index in range(100))
        + "\n--- FAIL: TestRefresh (0.01s)\n"
        + "FAIL example/auth 0.12s\n"
    )
    result = process_output(
        text,
        "go test ./...",
        exit_code=1,
        min_reduction=0.0,
    )
    assert result.processor == "go-test"
    assert "--- FAIL: TestRefresh" in result.text
    assert "FAIL example/auth" in result.text


def test_build_processor_keeps_compiler_error():
    """Build compression should retain compiler error evidence on failure."""
    text = (
        "\n".join(f"Compiling dependency_{index}" for index in range(160))
        + "\nerror: cannot find value session in this scope\n"
        + " --> src/main.rs:18:9\n"
        + "error: could not compile app\n"
    )
    result = process_output(
        text,
        "cargo build",
        exit_code=101,
        min_reduction=0.0,
    )
    assert result.processor == "cargo-build"
    assert "cannot find value" in result.text
    assert "src/main.rs:18:9" in result.text


def test_git_status_processor_retains_changed_files():
    """Git status compression should preserve changed-file inventory."""
    noise = "\n".join(f"hint line {index}" for index in range(120))
    text = (
        "On branch feature\n"
        "Changes not staged for commit:\n"
        "  modified: src/app.py\n"
        "Untracked files:\n"
        "  new.py\n"
        + noise
    )
    result = process_output(
        text,
        "git status",
        exit_code=0,
        min_reduction=0.0,
    )
    assert result.processor == "git-status"
    assert "modified: src/app.py" in result.text


def test_pip_install_uses_package_install_processor():
    """Python package installs should use the success-only install processor."""
    text = "\n".join(f"Downloading package-{index}" for index in range(120))
    text += "\nSuccessfully installed example-1.0\n"
    result = process_output(
        text,
        "pip install example",
        exit_code=0,
        min_reduction=0.0,
    )
    assert result.processor == "package-install"
