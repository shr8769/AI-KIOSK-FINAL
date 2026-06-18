"""
backend/tests/test_startup_performance.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Regression guard: backend import must complete in under 3 seconds.

Run before every demo and every commit touching backend/app/.
  pytest backend/tests/test_startup_performance.py -v

If this test fails, someone has added a heavy module-level import
(sentence_transformers, tensorflow, chromadb, torch, jax) outside
of the lazy getters in app.core.dependencies. Find it with:

  Get-ChildItem -Path backend/app -Recurse -Filter "*.py" |
    Select-String "import chromadb|import sentence_transformers|
                   import tensorflow|import torch|import jax" |
    Where-Object {$_ -notmatch "def |#"}
"""

import subprocess
import sys
import time
import os


STARTUP_BUDGET_SECONDS = 3.0


def test_backend_starts_under_3_seconds():
    """
    Measures wall-clock time for `from app.main import app` to complete.
    This catches any module-level heavy imports that slip past code review.
    """
    backend_dir = os.path.join(os.path.dirname(__file__), "..")
    start = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0,'backend'); from app.main import app; print('OK')"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=os.path.join(backend_dir, ".."),  # project root
    )
    elapsed = time.monotonic() - start

    output = result.stdout.strip() + result.stderr.strip()
    print(f"\nStartup time: {elapsed:.2f}s")
    print(f"Output: {output[:500]}")

    assert "OK" in result.stdout, (
        f"Backend failed to import:\n{result.stderr[:1000]}"
    )
    assert elapsed < STARTUP_BUDGET_SECONDS, (
        f"Backend import took {elapsed:.1f}s — exceeds {STARTUP_BUDGET_SECONDS}s budget.\n"
        f"Check for module-level heavy imports (sentence_transformers, tensorflow, chromadb) "
        f"outside of app.core.dependencies lazy getters.\n"
        f"Output: {output[:500]}"
    )
