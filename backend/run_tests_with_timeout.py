#!/usr/bin/env python3
"""
Test runner with timeout protection for regression testing.

This script runs backend checks with strict timeout limits while being resilient
to tools installed in local project folders such as `.testdeps` or `.venv`.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

DEFAULT_TIMEOUT = 300  # 5 minutes default timeout
BACKEND_DIR = Path(__file__).parent.resolve()
TESTDEPS_DIR = BACKEND_DIR / ".testdeps"
VENV_DIR = BACKEND_DIR / ".venv"


def _venv_python() -> Path:
    return VENV_DIR / "Scripts" / "python.exe"


def _tool_dirs() -> list[Path]:
    candidates = [
        VENV_DIR / "Scripts",
        VENV_DIR / "bin",
        TESTDEPS_DIR / "Scripts",
        TESTDEPS_DIR / "bin",
    ]
    return [path for path in candidates if path.exists()]


def _build_env() -> dict[str, str]:
    env = os.environ.copy()

    pythonpath_parts = []
    if TESTDEPS_DIR.exists() and not _venv_python().exists():
        pythonpath_parts.append(str(TESTDEPS_DIR))
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    if pythonpath_parts:
        env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    path_parts = [str(path) for path in _tool_dirs()]
    if env.get("PATH"):
        path_parts.append(env["PATH"])
    env["PATH"] = os.pathsep.join(path_parts)
    env.setdefault("PYTHONUTF8", "1")
    return env


def _python_cmd() -> list[str]:
    venv_python = _venv_python()
    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        return [str(venv_python)]
    return [sys.executable]


def _find_tool(tool_name: str) -> str | None:
    env = _build_env()
    resolved = shutil.which(tool_name, path=env.get("PATH"))
    if resolved:
        return resolved

    windows_name = f"{tool_name}.exe"
    for tool_dir in _tool_dirs():
        for candidate in (tool_dir / tool_name, tool_dir / windows_name):
            if candidate.exists():
                return str(candidate)
    return None


def _module_available(module_name: str) -> bool:
    check = subprocess.run(
        _python_cmd()
        + [
            "-c",
            (
                "import importlib.util, sys; "
                f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
            ),
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        env=_build_env(),
    )
    return check.returncode == 0


def run_command_with_timeout(cmd: list[str], timeout: int, description: str) -> bool:
    """Run a shell command with timeout protection."""
    print(f"\n{'=' * 60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"Timeout: {timeout} seconds")
    print("=" * 60)

    try:
        result = subprocess.run(
            cmd,
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_build_env(),
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if result.returncode != 0:
            print(f"\n[FAIL] {description} failed with exit code {result.returncode}")
            return False

        print(f"\n[PASS] {description} completed successfully")
        return True

    except subprocess.TimeoutExpired as ex:
        print(f"\n[FAIL] TIMEOUT: {description} exceeded {timeout} seconds")
        if ex.stdout:
            print(ex.stdout.decode() if isinstance(ex.stdout, bytes) else ex.stdout)
        if ex.stderr:
            print(
                ex.stderr.decode() if isinstance(ex.stderr, bytes) else ex.stderr,
                file=sys.stderr,
            )
        return False
    except Exception as ex:
        print(f"\n[FAIL] ERROR: {description} failed with exception: {ex}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run regression tests with timeout protection"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--lint-timeout",
        type=int,
        default=60,
        help="Timeout for linting (default: 60)",
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout for tests (default: {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args()

    results: list[bool] = []

    print("\nRunning static analysis...")

    ruff_cmd = _find_tool("ruff")
    if ruff_cmd:
        results.append(
            run_command_with_timeout(
                [ruff_cmd, "check", "app"],
                args.lint_timeout,
                "Linting with ruff",
            )
        )
        results.append(
            run_command_with_timeout(
                [ruff_cmd, "format", "app", "--check"],
                args.lint_timeout,
                "Format checking with ruff",
            )
        )
    else:
        print("\n[WARN] ruff not found, trying fallback linters")
        for linter in ("pylint", "flake8"):
            linter_cmd = _find_tool(linter)
            if linter_cmd:
                results.append(
                    run_command_with_timeout(
                        [linter_cmd, "app"],
                        args.lint_timeout,
                        f"Linting with {linter}",
                    )
                )
                break
        else:
            print("\n[WARN] No supported linter found, skipping linting")

    mypy_cmd = None
    if _module_available("mypy"):
        mypy_cmd = _python_cmd() + ["-m", "mypy"]
    else:
        external_mypy = _find_tool("mypy")
        if external_mypy:
            mypy_cmd = [external_mypy]

    if mypy_cmd:
        mypy_args = list(mypy_cmd)
        config_path = BACKEND_DIR / "mypy.ini"
        if config_path.exists():
            mypy_args += ["--config-file", str(config_path)]
        mypy_args.append("app")
        mypy_result = run_command_with_timeout(
            mypy_args,
            args.lint_timeout,
            "Type checking with mypy",
        )
        if not mypy_result:
            print("\n[WARN] Mypy found type issues, but continuing (non-blocking)")
    else:
        print("\n[WARN] mypy not installed, skipping type checking")

    test_dir = BACKEND_DIR / "tests"
    if test_dir.exists() or any(BACKEND_DIR.glob("test_*.py")):
        results.append(
            run_command_with_timeout(
                _python_cmd() + ["-m", "pytest", "-v", "--tb=short"],
                args.test_timeout,
                "Running pytest",
            )
        )
    else:
        print("\n[WARN] No test directory found, skipping pytest")

    results.append(
        run_command_with_timeout(
            _python_cmd() + ["-c", 'import app.main; print("Import successful")'],
            30,
            "Import sanity check",
        )
    )

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if all(results):
        print("\n[PASS] All checks passed!")
        return 0

    print("\n[FAIL] Some checks failed or timed out")
    return 1


if __name__ == "__main__":
    sys.exit(main())
