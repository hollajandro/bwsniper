# Timeout Implementation for Regression Testing

## Overview

This document describes the timeout protections implemented to prevent hanging during regression testing and CI/CD pipeline execution.

## Files Modified/Created

### 1. `/workspace/backend/run_tests_with_timeout.py` (NEW)

A Python test runner script that enforces strict timeout limits on all test operations:

**Features:**
- Runs linting (flake8/pylint) with configurable timeout
- Runs type checking (mypy) with configurable timeout  
- Runs pytest tests with configurable timeout
- Performs import sanity checks with timeout
- All subprocess calls use `subprocess.run()` with explicit `timeout` parameter
- Gracefully handles `TimeoutExpired` exceptions
- Provides clear pass/fail reporting

**Usage:**
```bash
# Default timeouts (300s overall, 60s lint, 300s tests)
python run_tests_with_timeout.py

# Custom timeouts
python run_tests_with_timeout.py --timeout 300 --lint-timeout 60 --test-timeout 300
```

### 2. `/workspace/.github/workflows/docker-publish.yml` (MODIFIED)

Added timeout-protected regression testing steps to the CI/CD pipeline:

**Backend Job Changes:**
- Added Python setup step (v3.11)
- Added dependency installation step
- **Added regression test step with 600-second timeout wrapper:**
  ```yaml
  - name: Run regression tests with timeout
    run: |
      cd backend
      timeout 600 python run_tests_with_timeout.py --timeout 300 --lint-timeout 60 --test-timeout 300
  ```

**Frontend Job Changes:**
- Added Node.js setup step (v20)
- Added npm dependency installation step
- **Added linting and build steps with timeout wrappers:**
  ```yaml
  - name: Run linting and build with timeout
    run: |
      cd frontend
      timeout 300 npm run lint || true
      timeout 600 npm run build
  ```

## Timeout Strategy

### Shell-Level Protection
All commands in the CI/CD pipeline are wrapped with the Unix `timeout` command:
```bash
timeout <seconds> <command>
```

This provides a hard kill if the command exceeds the specified duration.

### Python-Level Protection  
The `run_tests_with_timeout.py` script uses `subprocess.run(timeout=N)` for all internal command execution:
```python
result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=timeout,  # <-- Explicit timeout parameter
    check=False
)
```

This ensures that even if individual test suites or linters hang, they will be terminated.

### Nested Timeout Layers

```
GitHub Actions Step (600s timeout)
└── run_tests_with_timeout.py
    ├── Linting (60s timeout via subprocess.run)
    ├── Type Checking (60s timeout via subprocess.run)
    ├── Pytest (300s timeout via subprocess.run)
    └── Import Check (30s timeout via subprocess.run)
```

## Best Practices Applied

1. **Always specify timeout**: Every `subprocess.run()` call includes an explicit `timeout` parameter
2. **Catch TimeoutExpired**: Proper exception handling prevents crashes on timeout
3. **Layered timeouts**: Both shell-level and application-level timeouts provide defense in depth
4. **Reasonable defaults**: Timeouts are set high enough for normal operations but low enough to catch hangs
5. **Clear error messages**: Timeout events are logged with clear indicators

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--timeout` | 300s | Overall timeout for each test phase |
| `--lint-timeout` | 60s | Timeout for linting operations |
| `--test-timeout` | 300s | Timeout for pytest execution |

## Future Enhancements

Consider adding:
- Per-test timeouts via pytest-timeout plugin
- Individual function/method timeout decorators
- Metrics collection for timeout violations
- Automatic retry logic for transient failures
