import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def authenticated_ai(monkeypatch, tmp_path):
    """Explicit identity override for route behavior tests, never production."""
    from app.ai_access import require_ai_user
    from app.main import app
    monkeypatch.setenv("AI_USAGE_DB_PATH", str(tmp_path / "usage.sqlite3"))
    app.dependency_overrides[require_ai_user] = lambda: {
        "sub": "test-user", "email": "test@example.com", "expires_at": time.time() + 3600}
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_ai_user, None)
