import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import duckdb
import numpy as np
import pytest
from fastapi.testclient import TestClient
from google import genai
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import errors, types
from pydantic import Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import chat, main
from app.data import db


class ScriptedModel(BaseLlm):
    model: str = "test-model"
    responses: list[LlmResponse]
    requests: list[Any] = Field(default_factory=list)

    async def generate_content_async(self, llm_request, stream=False):
        self.requests.append(llm_request.model_copy(deep=True))
        yield self.responses.pop(0)


def response(*parts):
    return LlmResponse(content=types.Content(role="model", parts=list(parts)))


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "test.duckdb"
    with duckdb.connect(str(path)) as conn:
        conn.execute("CREATE TABLE sample AS SELECT range AS value FROM range(150)")
    monkeypatch.setattr(db, "DB_PATH", path)
    return path


def test_real_adk_tool_loop_and_history(database, monkeypatch):
    monkeypatch.setattr(chat, "_system_instruction", lambda: "Use dashboard tools.")
    model = ScriptedModel(responses=[
        response(types.Part.from_function_call(name="query_database", args={"sql": "SELECT * FROM sample"})),
        response(types.Part.from_text(text="There are 150 rows; showing the first 100.")),
    ])
    history = [{"role": "user", "content": "Remember SPY"},
               {"role": "assistant", "content": "SPY selected"},
               {"role": "user", "content": "Read the sample"}]
    results = []
    text = asyncio.run(chat._run_adk(history, results, model))
    assert "150 rows" in text
    assert len(model.requests) == 2
    first = model.requests[0]
    assert [(c.role, c.parts[0].text) for c in first.contents] == [
        ("user", "Remember SPY"), ("model", "SPY selected"), ("user", "Read the sample")]
    assert {f.name for tool in first.config.tools for f in tool.function_declarations} == set(chat.TOOL_HANDLERS)
    assert results[0]["tool"] == "query_database"
    assert results[0]["output"]["truncated"] is True
    assert len(results[0]["output"]["rows"]) == 100
    assert any(p.function_response for c in model.requests[1].contents for p in c.parts)


def test_concurrent_sessions_are_isolated(monkeypatch):
    monkeypatch.setattr(chat, "_system_instruction", lambda: "Test")

    async def run():
        async def one(label):
            model = ScriptedModel(responses=[response(types.Part.from_text(text=label))])
            result = await chat._run_adk([{"role": "user", "content": label}], [], model)
            assert model.requests[0].contents[0].parts[0].text == label
            return result
        return await asyncio.gather(one("first"), one("second"))
    assert asyncio.run(run()) == ["first", "second"]


def test_read_only_database_and_external_access(database, tmp_path):
    with duckdb.connect(str(database), read_only=True):
        with db.isolated_read_db() as conn:
            assert db.get_db() is conn
            assert conn.execute("SELECT count(*) FROM sample").fetchone() == (150,)
            with pytest.raises(duckdb.Error):
                conn.execute("DELETE FROM sample")
            with pytest.raises(duckdb.Error):
                conn.execute(f"SELECT * FROM read_text('{database}')")
            with pytest.raises(ValueError):
                db.get_db(read_only=False)
            assert "error" in chat._query_database_tool({"sql": "SELECT 1; SELECT 2"})
            assert "error" in chat._query_database_tool({"sql": "DELETE FROM sample"})
    assert db._scoped_reader.get() is None


def test_tool_validation_and_budget(database):
    definition = next(t for t in chat.TOOL_DEFS if t["name"] == "query_database")
    results, budget = [], {"calls": 0}
    tool = chat.DashboardTool(definition, results, budget)
    invalid = asyncio.run(tool.run_async(args={}, tool_context=None))
    assert "Invalid tool arguments" in invalid["error"]
    budget["calls"] = 20
    assert "budget" in asyncio.run(tool.run_async(args={"sql": "SELECT 1"}, tool_context=None))["error"]


@pytest.mark.parametrize("messages", [[], "hello", [{"role": "system", "content": "bad"}],
    [{"role": "assistant", "content": "hi"}], [{"role": "user", "content": " "}],
    [{"role": "user", "content": "x" * 60001}]])
def test_message_validation(messages):
    with pytest.raises(ValueError):
        asyncio.run(chat.run_chat(messages))


def test_missing_google_key_does_not_use_anthropic(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unused")
    assert "GOOGLE_API_KEY" in asyncio.run(chat.run_chat([{"role": "user", "content": "hi"}]))["response"]


@pytest.mark.parametrize("code,message,expected", [
    (400, "API key not valid", "GOOGLE_API_KEY"), (403, "Forbidden", "GOOGLE_API_KEY"),
    (402, "Your prepayment credits are depleted", "prepaid credits"),
    (429, "Quota", "quota"), (404, "Model missing", "CHAT_MODEL"),
])
def test_provider_errors_and_client_cleanup(monkeypatch, code, message, expected):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    client = MagicMock()
    client.aio.aclose = AsyncMock()
    monkeypatch.setattr(genai, "Client", MagicMock(return_value=client))
    monkeypatch.setattr(chat, "Gemini", lambda **kwargs: kwargs)
    monkeypatch.setattr(chat, "_run_adk", AsyncMock(side_effect=errors.ClientError(
        code, {"error": {"code": code, "message": message}})))
    result = asyncio.run(chat.run_chat([{"role": "user", "content": "hi"}]))
    assert expected in result["response"]
    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()


def test_route_ignores_legacy_provider(monkeypatch, authenticated_ai):
    run = AsyncMock(return_value={"response": "Gemini", "tool_results": []})
    monkeypatch.setattr(chat, "run_chat", run)
    messages = [{"role": "user", "content": "hi"}]
    result = TestClient(main.app).post("/chat", json={"messages": messages, "provider": "anthropic"})
    assert result.status_code == 200
    run.assert_awaited_once_with(messages)


def test_json_safe():
    assert chat._json_safe({"date": date(2026, 11, 13), "value": np.float64("nan"),
                           "values": (np.int64(2), float("inf"))}) == {
        "date": "2026-11-13", "value": None, "values": [2, None]}


def test_theta_tool_matches_dashboard_quality_policy(monkeypatch):
    from app import theta_quality
    from test_theta_quality import candidate, NOW, SCAN

    rows = [candidate(), candidate(ticker="BAD", rank_score=0)]
    original = theta_quality.scan_response
    monkeypatch.setattr(theta_quality, "scan_response", lambda rows, scan: original(rows, scan, now=NOW))
    monkeypatch.setattr(db, "get_latest_theta_scan_by_expiry", lambda expiry: SCAN)
    monkeypatch.setattr(db, "get_theta_results", lambda scan_id: rows)
    result = chat._get_theta_plays_tool({"expiry": SCAN["expiry"]})
    assert [r["ticker"] for r in result["results"]] == ["SPY"]
    assert result["quality_counts"] == {"eligible": 1, "total": 2}


def test_prompt_defaults_are_refreshed_each_turn(database, monkeypatch):
    values = {"today": "2026-11-13", "earliest_data_date": "2025-01-02", "latest_data_date": "2026-11-12"}
    monkeypatch.setattr(chat, "_prompt_defaults", lambda: values)
    assert "through 2026-11-12" in chat._system_instruction()
    values["latest_data_date"] = "2026-11-13"
    assert "through 2026-11-13" in chat._system_instruction()


def test_default_and_override_model(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    client = MagicMock()
    client.aio.aclose = AsyncMock()
    monkeypatch.setattr(genai, "Client", MagicMock(return_value=client))
    model = MagicMock()
    monkeypatch.setattr(chat, "Gemini", model)
    monkeypatch.setattr(chat, "_run_adk", AsyncMock(return_value="Done"))
    monkeypatch.delenv("CHAT_MODEL", raising=False)
    asyncio.run(chat.run_chat([{"role": "user", "content": "hi"}]))
    assert model.call_args.kwargs["model"] == "gemini-3.8-flash"
    monkeypatch.setenv("CHAT_MODEL", "custom-flash")
    asyncio.run(chat.run_chat([{"role": "user", "content": "hi"}]))
    assert model.call_args.kwargs["model"] == "custom-flash"
