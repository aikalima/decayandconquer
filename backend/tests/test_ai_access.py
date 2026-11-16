import asyncio
import json
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.auth.exceptions import TransportError
from google.genai import types

from app import ai_access, ai_usage, chat, main


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_USAGE_DB_PATH", str(tmp_path / "usage.sqlite3"))
    for key in ("AI_REQUESTS_PER_MINUTE", "AI_REQUESTS_PER_DAY", "AI_REQUESTS_PER_MONTH",
                "AI_USER_REQUESTS_PER_DAY", "AI_USER_REQUESTS_PER_MONTH", "AI_MAX_CONCURRENT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client.apps.googleusercontent.com")
    ai_access._verify.cache_clear()
    yield
    ai_access._verify.cache_clear()


def claims(**overrides):
    return {"sub": "google-user-1", "email": "visitor@example.com", "email_verified": True,
            "exp": time.time() + 3600, **overrides}


@pytest.mark.parametrize("invalid", [None, "audience", "issuer", "expiry", "signature"])
def test_real_google_verifier_checks_signed_token(monkeypatch, invalid):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from google.auth import crypt, jwt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-only")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(1).not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    certificate_requests = []
    def fetch_certificate(url, *, method, timeout):
        certificate_requests.append((url, method, timeout))
        return SimpleNamespace(status=200, data=json.dumps({
            "test-key": certificate.public_bytes(serialization.Encoding.PEM).decode()
        }).encode())
    # Stub HTTP only, preserving Google's positional transport call and the
    # complete certificate-fetch, signature-verification and route path.
    monkeypatch.setattr(ai_access, "Request", lambda: fetch_certificate)
    if invalid == "signature":
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    payload = claims(iss="https://accounts.google.com", iat=int(time.time()) - 100,
                     exp=int(time.time()) + 3600, aud="test-client.apps.googleusercontent.com")
    if invalid == "audience":
        payload["aud"] = "other-client"
    elif invalid == "issuer":
        payload["iss"] = "https://attacker.example"
    elif invalid == "expiry":
        payload["exp"] = int(time.time()) - 10
    signed = jwt.encode(crypt.RSASigner.from_string(pem, key_id="test-key"), payload).decode()
    with TestClient(main.app) as client:
        result = client.get("/ai-access/status", headers={"Authorization": f"Bearer {signed}"})
    assert result.status_code == (401 if invalid else 200)
    if not invalid:
        assert result.json()["user"]["sub"] == payload["sub"]
    assert certificate_requests == [("https://www.googleapis.com/oauth2/v1/certs", "GET", 10)]


def test_certificate_transport_failure_returns_safe_error():
    from unittest.mock import patch
    def unavailable(url, *, method, timeout):
        raise TransportError("Certificate service unavailable")
    with patch.object(ai_access, "Request", return_value=unavailable), TestClient(main.app) as client:
        result = client.get("/ai-access/status", headers={"Authorization": "Bearer test-token"})
    assert result.status_code == 503
    assert result.json()["detail"] == "Google sign-in verification is temporarily unavailable."


@pytest.mark.parametrize("endpoint", ["/chat", "/market-context"])
def test_anonymous_cannot_spend(endpoint, monkeypatch):
    run = AsyncMock()
    monkeypatch.setattr(chat, "run_chat", run)
    with TestClient(main.app) as client:
        response = client.post(endpoint, json={"messages": [{"role": "user", "content": "hi"}]}) if endpoint == "/chat" else client.get(endpoint)
    assert response.status_code == 401
    run.assert_not_called()
    assert ai_usage.usage_summary("any")["monthly_requests"] == 0


def test_missing_configuration_fails_closed_public_dashboard_stays_up(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID")
    with TestClient(main.app) as client:
        assert client.get("/ai-access/config").json() == {"client_id": "", "configured": False}
        assert client.get("/market-context").status_code == 503
        assert client.get("/ping").status_code == 200


def test_google_library_verifies_audience_and_caches_only_valid_tokens(monkeypatch):
    calls = []
    def verify(token, request, audience):
        calls.append((token, audience))
        if token == "invalid":
            raise ValueError("bad signature")
        return claims()
    monkeypatch.setattr(ai_access.id_token, "verify_oauth2_token", verify)
    for _ in range(2):
        assert ai_access.require_ai_user("Bearer valid")["email"] == "visitor@example.com"
    assert calls == [("valid", "test-client.apps.googleusercontent.com")]
    with pytest.raises(HTTPException) as exc:
        ai_access.require_ai_user("Bearer invalid")
    assert exc.value.status_code == 401


@pytest.mark.parametrize("overrides", [{"exp": 0}, {"email_verified": False}, {"sub": ""}])
def test_invalid_claims_rejected(monkeypatch, overrides):
    monkeypatch.setattr(ai_access.id_token, "verify_oauth2_token", lambda *a, **k: claims(**overrides))
    with pytest.raises(HTTPException) as exc:
        ai_access.require_ai_user("Bearer token")
    assert exc.value.status_code == 401


def test_cached_tokens_expire_and_provider_failure_is_not_an_auth_bypass(monkeypatch):
    now = time.time()
    monkeypatch.setattr(ai_access.id_token, "verify_oauth2_token", lambda *a, **k: claims(exp=now + 5))
    ai_access.require_ai_user("Bearer token")
    monkeypatch.setattr(ai_access.time, "time", lambda: now + 6)
    with pytest.raises(HTTPException) as exc:
        ai_access.require_ai_user("Bearer token")
    assert exc.value.status_code == 401
    def unavailable(*args, **kwargs):
        raise TransportError("network unavailable")
    monkeypatch.setattr(ai_access.id_token, "verify_oauth2_token", unavailable)
    with pytest.raises(HTTPException) as exc:
        ai_access.require_ai_user("Bearer other-token")
    assert exc.value.status_code == 503


def test_all_google_accounts_welcome_and_spoofed_identity_headers_ignored(monkeypatch):
    monkeypatch.setattr(ai_access.id_token, "verify_oauth2_token", lambda token, *a, **k: claims(sub=token))
    run = AsyncMock(return_value={"response": "OK", "tool_results": []})
    monkeypatch.setattr(chat, "run_chat", run)
    monkeypatch.setenv("AI_REQUESTS_PER_MINUTE", "1")
    with TestClient(main.app) as client:
        def send(token, ip):
            return client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]},
                               headers={"Authorization": f"Bearer {token}", "X-Forwarded-For": ip, "X-User-ID": ip})
        assert send("account-one", "1.1.1.1").status_code == 200
        limited = send("account-one", "2.2.2.2")
        assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
        assert send("account-two", "1.1.1.1").status_code == 200
        response = client.get("/ai-access/status", headers={"Authorization": "Bearer account-two"})
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["usage"]["your_monthly_requests"] == 1
    assert run.await_count == 2


def test_failed_attempts_count_and_usage_captures_threads(monkeypatch):
    async def run():
        with ai_usage.metered_request("one", "/market-context"):
            await asyncio.to_thread(ai_usage.record_usage, SimpleNamespace(usage_metadata=SimpleNamespace(
                prompt_token_count=100, candidates_token_count=20, thoughts_token_count=5, total_token_count=125)))
            ai_usage.mark_failed()
    asyncio.run(run())
    with ai_usage.connection() as conn:
        row = conn.execute("SELECT * FROM ai_requests").fetchone()
        assert row["status"] == "failed" and row["finished"] is not None
        assert row["total_tokens"] == 125 and row["model_responses"] == 1
    assert ai_usage.usage_summary("one")["monthly_requests"] == 1
    assert ai_usage.usage_summary("other")["your_reported_total_tokens"] == 0
    assert ai_usage._current.get() is None


@pytest.mark.parametrize("env", ["AI_REQUESTS_PER_DAY", "AI_REQUESTS_PER_MONTH",
                                  "AI_USER_REQUESTS_PER_DAY", "AI_USER_REQUESTS_PER_MONTH"])
def test_hard_budgets(env, monkeypatch):
    monkeypatch.setenv(env, "1")
    with ai_usage.metered_request("one", "/chat"):
        pass
    with pytest.raises(HTTPException) as exc:
        ai_usage.reserve("one", "/market-context")
    assert exc.value.status_code == 429
    assert ai_usage.usage_summary("one")["monthly_requests"] == 1


def test_default_daily_credit_allowance_reaches_100_without_a_lower_cap(monkeypatch):
    now = datetime(2026, 11, 16, 1, tzinfo=timezone.utc).timestamp()
    for index in range(100):
        monkeypatch.setattr(ai_usage.time, "time", lambda: now + index * 61)
        with ai_usage.metered_request("one", "/chat"):
            pass
    summary = ai_usage.usage_summary("one")
    assert summary["your_daily_requests"] == 100
    assert summary["limits"]["per_user_daily"] == 100
    assert summary["limits"]["monthly"] == 200
    with pytest.raises(HTTPException) as exc:
        ai_usage.reserve("one", "/market-context")
    assert exc.value.status_code == 429
    assert "daily" in exc.value.detail


def test_utc_period_rollover_and_rolling_minute(monkeypatch):
    now = datetime(2026, 11, 30, 23, 59, 50, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(ai_usage.time, "time", lambda: now)
    monkeypatch.setenv("AI_REQUESTS_PER_MONTH", "1")
    with ai_usage.metered_request("one", "/chat"):
        pass
    monkeypatch.setattr(ai_usage.time, "time", lambda: now + 61)
    with ai_usage.metered_request("one", "/chat"):
        pass
    assert ai_usage.usage_summary("one")["monthly_requests"] == 1


def test_active_limit_and_crashed_worker_lease(monkeypatch):
    now = time.time()
    monkeypatch.setenv("AI_MAX_CONCURRENT", "1")
    ai_usage.reserve("one", "/chat")
    with pytest.raises(HTTPException) as exc:
        ai_usage.reserve("two", "/chat")
    assert exc.value.status_code == 429
    monkeypatch.setattr(ai_usage.time, "time", lambda: now + 601)
    ai_usage.reserve("two", "/chat")
    with ai_usage.connection() as conn:
        assert conn.execute("SELECT status FROM ai_requests WHERE subject='one'").fetchone()[0] == "abandoned"
    assert ai_usage.usage_summary("one")["monthly_requests"] == 2


def _competing_worker(_):
    try:
        ai_usage.reserve("one", "/chat")
        return 200
    except HTTPException as exc:
        return exc.status_code


def test_multiple_processes_cannot_overspend(monkeypatch):
    monkeypatch.setenv("AI_REQUESTS_PER_MONTH", "2")
    monkeypatch.setenv("AI_MAX_CONCURRENT", "20")
    with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(_competing_worker, range(6)))
    assert sorted(results) == [200, 200, 429, 429, 429, 429]


def test_storage_failure_and_invalid_limits_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_USAGE_DB_PATH", str(tmp_path))
    with pytest.raises(HTTPException) as exc:
        ai_usage.reserve("one", "/chat")
    assert exc.value.status_code == 503
    monkeypatch.setenv("AI_REQUESTS_PER_DAY", "not-a-number")
    with pytest.raises(HTTPException) as exc:
        ai_usage.limits()
    assert exc.value.status_code == 503


def test_exception_releases_slot_but_keeps_charge():
    with pytest.raises(RuntimeError):
        with ai_usage.metered_request("one", "/chat"):
            raise RuntimeError("provider failed")
    with ai_usage.connection() as conn:
        assert conn.execute("SELECT status FROM ai_requests").fetchone()[0] == "failed"


def test_cors_is_not_wildcard():
    with TestClient(main.app) as client:
        response = client.options("/chat", headers={"Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"})
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers


def test_invalid_context_input_cannot_reach_google(authenticated_ai, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.setattr(main, "build_app_defaults", lambda: {"prediction": {}})
    monkeypatch.setattr(main, "fetch_market_context", lambda *args: pytest.fail("Must not call Google"))
    with TestClient(main.app) as client:
        response = client.get("/market-context", params={"ticker": "SPY", "obs_from": "bad", "obs_to": "2026-11-12"})
    assert "valid observation dates" in response.json()["error"]


def test_adk_usage_is_recorded_for_every_model_response(monkeypatch):
    from test_chat_adk import ScriptedModel, response
    monkeypatch.setattr(chat, "_system_instruction", lambda: "Test")
    answer = response(types.Part.from_text(text="Hello"))
    answer.usage_metadata = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=100, candidates_token_count=20, total_token_count=120)
    model = ScriptedModel(responses=[answer])
    with ai_usage.metered_request("one", "/chat"):
        assert asyncio.run(chat._run_adk([{"role": "user", "content": "Hi"}], [], model)) == "Hello"
    assert ai_usage.usage_summary("one")["your_reported_total_tokens"] == 120
