"""Test setup: point the app at a fresh, throwaway SQLite database.

This runs before any test module imports the app, so app.db picks up the temp
DATABASE_URL and creates clean tables — keeping tests isolated from any real
dev database and from each other's leftovers between runs.
"""

import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

# Don't throttle the test suite.
os.environ["RATE_LIMIT_ENABLED"] = "false"
