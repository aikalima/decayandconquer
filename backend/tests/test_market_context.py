import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import errors

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import news, main

EVENT = {"date": "2026-11-10", "headline": "Market event", "category": "macro",
         "impact": "Changed volatility expectations", "source": "Example source"}
PAYLOAD = json.dumps({"events": [EVENT]})


@pytest.mark.parametrize("text", [PAYLOAD, f"```json\n{PAYLOAD}\n```",
    f"Based on search results, here is the JSON:\n{PAYLOAD}",
    f"Preface {{not json}}\n```json\n{PAYLOAD}\n```\nEnd."])
def test_json_wrappers_are_tolerated(text):
    assert news._parse_events(text) == [EVENT]


@pytest.mark.parametrize("text", [None, "", "No JSON", '{"events": [',
                                  '{"events": {}}', '{"other": []}'])
def test_invalid_output_is_not_silently_empty(text):
    with pytest.raises(news.MarketContextError):
        news._parse_events(text)


def test_event_shape_and_date_range_validation():
    assert news._validate_events([None, 1, {}, EVENT, {**EVENT, "date": "2020-01-01"},
                                 {**EVENT, "date": "bad"}], "2026-11-01", "2026-11-12") == [EVENT]


@pytest.fixture
def google_client(monkeypatch):
    state = SimpleNamespace(error=None,
        text=json.dumps({"events": [{**EVENT, "evidence_ids": [0]}]}), finish="STOP", format_finish="STOP",
        chunks=[SimpleNamespace(web=SimpleNamespace(title="Example source", uri="https://example.com/news"))],
        supports=[SimpleNamespace(segment=SimpleNamespace(text="2026-11-10: Market event."),
                                  grounding_chunk_indices=[0])], calls=[])
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("MARKET_CONTEXT_MODEL", raising=False)

    class Client:
        def __init__(self, **kwargs):
            state.client_args = kwargs
            self.models = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def generate_content(self, **kwargs):
            state.calls.append(kwargs)
            if state.error:
                raise state.error
            search = bool(kwargs["config"].tools)
            return SimpleNamespace(text="Uncited material must not reach formatter" if search else state.text,
                usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=20, total_token_count=120),
                candidates=[SimpleNamespace(finish_reason=state.finish if search else state.format_finish,
                    grounding_metadata=SimpleNamespace(grounding_chunks=state.chunks,
                                                       grounding_supports=state.supports) if search else None)])

    monkeypatch.setattr(genai, "Client", Client)
    assert not hasattr(news, "fetch_market_context_anthropic")
    return state


def test_flash_lite_searches_before_formatting_only_cited_evidence(google_client):
    assert news.fetch_market_context("SPY", "2026-11-01", "2026-11-12") == [EVENT]
    request = google_client.calls[0]
    assert len(google_client.calls) == 2
    assert request["model"] == "gemini-3.5-flash-lite"
    assert request["config"].response_mime_type is None
    assert request["config"].response_json_schema is None
    assert request["config"].tools[0].google_search is not None
    formatted = google_client.calls[1]
    assert formatted["model"] == request["model"]
    assert formatted["config"].response_mime_type == "application/json"
    assert formatted["config"].response_json_schema == news.EVENT_SCHEMA
    assert not formatted["config"].tools
    assert "2026-11-10: Market event." in formatted["contents"]
    assert "Uncited material" not in formatted["contents"]
    assert google_client.client_args["http_options"].timeout == 45000


def test_model_override_does_not_use_chat_model(google_client, monkeypatch):
    monkeypatch.setenv("MARKET_CONTEXT_MODEL", "gemini-custom-flash")
    monkeypatch.setenv("ANTHROPIC_MODEL", "chat-only")
    news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")
    assert google_client.calls[0]["model"] == "gemini-custom-flash"


def test_both_search_and_format_usage_are_recorded(google_client, authenticated_ai):
    from app import ai_usage
    with ai_usage.metered_request("test-user", "/market-context"):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")
    with ai_usage.connection() as conn:
        row = conn.execute("SELECT model_responses,total_tokens FROM ai_requests").fetchone()
        assert tuple(row) == (2, 240)


@pytest.mark.parametrize("code,message,expected", [
    (400, "API key not valid.", "GOOGLE_API_KEY"),
    (402, "Your prepayment credits are depleted", "prepaid credits"),
    (403, "Permission denied", "GOOGLE_API_KEY"),
    (429, "Resource exhausted", "quota"),
    (404, "Not found", "MARKET_CONTEXT_MODEL"),
])
def test_provider_failures_are_actionable(google_client, code, message, expected):
    google_client.error = errors.ClientError(code, {"error": {"code": code, "message": message}})
    with pytest.raises(news.MarketContextError, match=expected):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")


def test_no_sources_or_truncated_answer_is_an_error(google_client):
    google_client.chunks = []
    with pytest.raises(news.MarketContextError, match="sources"):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")
    assert len(google_client.calls) == 1
    google_client.finish = "MAX_TOKENS"
    with pytest.raises(news.MarketContextError, match="finish"):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")


def test_sources_without_supported_segments_are_rejected(google_client):
    google_client.supports = []
    with pytest.raises(news.MarketContextError, match="sources"):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")
    assert len(google_client.calls) == 1


def test_formatting_must_finish(google_client):
    google_client.format_finish = "MAX_TOKENS"
    with pytest.raises(news.MarketContextError, match="finish"):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")


@pytest.mark.parametrize("ids", [None, [], [-1], [1], [True], ["0"], [0, 99]])
def test_invalid_evidence_references_are_rejected(google_client, ids):
    google_client.text = json.dumps({"events": [{**EVENT, "evidence_ids": ids}]})
    with pytest.raises(news.MarketContextError, match="no valid events"):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")


def test_source_is_taken_from_metadata_not_formatter(google_client):
    google_client.text = json.dumps({"events": [{**EVENT, "source": "Invented publisher", "evidence_ids": [0]}]})
    assert news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")[0]["source"] == "Example source"


def test_empty_success_and_invalid_events_differ(google_client):
    google_client.text = '{"events": []}'
    assert news.fetch_market_context("SPY", "2026-11-01", "2026-11-12") == []
    google_client.text = '{"events": [null]}'
    with pytest.raises(news.MarketContextError, match="no valid events"):
        news.fetch_market_context("SPY", "2026-11-01", "2026-11-12")


def test_route_requires_google_not_anthropic_key(monkeypatch, authenticated_ai):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "present-but-unused")
    payload = TestClient(main.app).get('/market-context').json()
    assert "GOOGLE_API_KEY" in payload["error"]
    assert not payload["events"]


def test_route_surfaces_error_without_raw_provider_details(monkeypatch, authenticated_ai):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr(main, "build_app_defaults", lambda: {"prediction": {
        "obs_date_from": "2026-11-01", "obs_date_to": "2026-11-12"}})
    def fail(*args):
        raise news.MarketContextError("Google rejected the Market Context API key.")
    monkeypatch.setattr(main, "fetch_market_context", fail)
    payload = TestClient(main.app).get('/market-context').json()
    assert "rejected" in payload["error"]
    assert payload["disclaimer"] == ""


def test_route_identifies_google_on_success(monkeypatch, authenticated_ai):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(main, "build_app_defaults", lambda: {"prediction": {
        "obs_date_from": "2026-11-01", "obs_date_to": "2026-11-12"}})
    monkeypatch.setattr(main, "fetch_market_context", lambda *args: [EVENT])
    payload = TestClient(main.app).get('/market-context').json()
    assert payload["events"] == [EVENT]
    assert "Google Search" in payload["disclaimer"]
    assert "error" not in payload
