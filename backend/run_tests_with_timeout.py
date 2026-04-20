#!/usr/bin/env python3
"""
Test runner with timeout protection for regression testing.

This script runs all tests with strict timeout limits to prevent hanging.
Usage:
    python run_tests_with_timeout.py [--timeout SECONDS]
"""

import sys
import subprocess
import argparse
import os
from pathlib import Path

DEFAULT_TIMEOUT = 300  # 5 minutes default timeout
BACKEND_DIR = Path(__file__).parent.resolve()


def run_command_with_timeout(cmd, timeout, description):
    """Run a shell command with timeout protection."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"Timeout: {timeout} seconds")
    print('='*60)
    
    try:
        result = subprocess.run(
            cmd,
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
            
        if result.returncode != 0:
            print(f"\n❌ {description} failed with exit code {result.returncode}")
            return False
        else:
            print(f"\n✅ {description} completed successfully")
            return True
            
    except subprocess.TimeoutExpired as e:
        print(f"\n❌ TIMEOUT: {description} exceeded {timeout} seconds")
        if e.stdout:
            print(e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout)
        if e.stderr:
            print(e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr, file=sys.stderr)
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {description} failed with exception: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Run regression tests with timeout protection')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT,
                        help=f'Timeout in seconds (default: {DEFAULT_TIMEOUT})')
    parser.add_argument('--lint-timeout', type=int, default=60,
                        help='Timeout for linting (default: 60)')
    parser.add_argument('--test-timeout', type=int, default=DEFAULT_TIMEOUT,
                        help='Timeout for tests (default: {DEFAULT_TIMEOUT})')
    args = parser.parse_args()
    
    results = []
    
    # Step 1: Linting (if pylint or flake8 is available)
    print("\n📋 Running static analysis...")
    for linter, cmd in [
        ('pylint', ['pylint', 'app']),
        ('flake8', ['flake8', 'app']),
    ]:
        try:
            # Check if linter exists
            subprocess.run([linter, '--version'], capture_output=True, timeout=5, check=False)
            results.append(run_command_with_timeout(
                cmd, 
                args.lint_timeout, 
                f'Linting with {linter}'
            ))
            break  # Use first available linter
        except FileNotFoundError:
            continue
    
    # Step 2: Type checking with mypy (if available)
    try:
        subprocess.run(['mypy', '--version'], capture_output=True, timeout=5, check=False)
        results.append(run_command_with_timeout(
            ['mypy', 'app'],
            args.lint_timeout,
            'Type checking with mypy'
        ))
    except FileNotFoundError:
        print("\n⚠️  mypy not installed, skipping type checking")
    
    # Step 3: Run pytest if tests exist
    test_dir = BACKEND_DIR / 'tests'
    if test_dir.exists() or any(BACKEND_DIR.glob('test_*.py')):
        results.append(run_command_with_timeout(
            ['python', '-m', 'pytest', '-v', '--tb=short'],
            args.test_timeout,
            'Running pytest'
        ))
    else:
        print("\n⚠️  No test directory found, skipping pytest")
    
    # Step 4: Import check (basic sanity test)
    results.append(run_command_with_timeout(
        ['python', '-c', 'import app.main; print("Import successful")'],
        30,
        'Import sanity check'
    ))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    
    if all(results):
        print("\n✅ All checks passed!")
        return 0
    else:
        print("\n❌ Some checks failed or timed out")
        return 1


if __name__ == '__main__':
    sys.exit(main())
