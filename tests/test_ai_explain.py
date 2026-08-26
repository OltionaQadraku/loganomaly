import json
from unittest.mock import MagicMock, patch

import src.ai_explain as ai_explain


def _reset_client_cache():
    """The client is lazily built and cached at module level -- reset it
    between tests so one test's env var / mock doesn't leak into another."""
    ai_explain._client = None
    ai_explain._client_checked = False


def _fake_completion(text):
    message = MagicMock(content=text)
    choice = MagicMock(message=message)
    return MagicMock(choices=[choice])


def test_ai_disabled_without_api_key(monkeypatch):
    _reset_client_cache()
    monkeypatch.delenv('GROQ_API_KEY', raising=False)

    assert ai_explain.ai_enabled() is False
    assert ai_explain.explain_evidence_lines(
        [{'level': 'ERROR', 'text': 'Database connection failed'}]) == {}


def test_ai_explain_returns_empty_for_no_evidence(monkeypatch):
    _reset_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    assert ai_explain.explain_evidence_lines([]) == {}


def test_ai_explain_parses_json_response(monkeypatch):
    _reset_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion(json.dumps({
        '0': 'The payment gateway rejected the request with a server-side error.',
    }))

    with patch('groq.Groq', return_value=fake_client):
        result = ai_explain.explain_evidence_lines(
            [{'level': 'ERROR', 'text': 'Payment gateway returned HTTP 503'}])

    assert result == {0: 'The payment gateway rejected the request with a server-side error.'}
    assert ai_explain.ai_enabled() is True


def test_ai_explain_falls_back_silently_on_api_error(monkeypatch):
    _reset_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = Exception('network error')

    with patch('groq.Groq', return_value=fake_client):
        result = ai_explain.explain_evidence_lines(
            [{'level': 'ERROR', 'text': 'Database connection failed'}])

    assert result == {}


def test_ai_explain_falls_back_silently_on_malformed_json(monkeypatch):
    _reset_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion('not valid json at all')

    with patch('groq.Groq', return_value=fake_client):
        result = ai_explain.explain_evidence_lines(
            [{'level': 'ERROR', 'text': 'Database connection failed'}])

    assert result == {}


def test_ai_explain_ignores_out_of_range_indices(monkeypatch):
    _reset_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion(json.dumps({
        '0': 'Valid explanation.',
        '7': 'This index does not exist in the request.',
    }))

    with patch('groq.Groq', return_value=fake_client):
        result = ai_explain.explain_evidence_lines(
            [{'level': 'ERROR', 'text': 'Database connection failed'}])

    assert result == {0: 'Valid explanation.'}


def test_explain_evidence_for_anomalies_without_api_key_returns_empties(monkeypatch):
    _reset_client_cache()
    monkeypatch.delenv('GROQ_API_KEY', raising=False)

    evidence_by_anomaly = [
        [{'level': 'ERROR', 'text': 'A'}],
        [{'level': 'ERROR', 'text': 'B'}],
    ]
    result = ai_explain.explain_evidence_for_anomalies(evidence_by_anomaly)
    assert result == [{}, {}]


def test_explain_evidence_for_anomalies_matches_results_to_the_right_anomaly(monkeypatch):
    _reset_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    def fake_create(*, model, messages, response_format):
        contents = messages[0]['content']
        if 'Database' in contents:
            text = json.dumps({'0': 'Explanation for the database anomaly.'})
        else:
            text = json.dumps({'0': 'Explanation for the payment anomaly.'})
        return _fake_completion(text)

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = fake_create

    evidence_by_anomaly = [
        [{'level': 'ERROR', 'text': 'Database connection failed'}],
        [{'level': 'ERROR', 'text': 'Payment gateway returned HTTP 503'}],
    ]

    with patch('groq.Groq', return_value=fake_client):
        result = ai_explain.explain_evidence_for_anomalies(evidence_by_anomaly)

    assert result[0] == {0: 'Explanation for the database anomaly.'}
    assert result[1] == {0: 'Explanation for the payment anomaly.'}


def test_explain_evidence_for_anomalies_caps_how_many_get_ai_calls(monkeypatch):
    _reset_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion(json.dumps({'0': 'Explained.'}))

    evidence_by_anomaly = [[{'level': 'ERROR', 'text': f'Error {i}'}] for i in range(5)]

    with patch('groq.Groq', return_value=fake_client):
        result = ai_explain.explain_evidence_for_anomalies(evidence_by_anomaly, max_anomalies=2)

    assert result[0] == {0: 'Explained.'}
    assert result[1] == {0: 'Explained.'}
    assert result[2] == {}
    assert result[3] == {}
    assert result[4] == {}
    assert fake_client.chat.completions.create.call_count == 2


def test_explain_evidence_for_anomalies_empty_input():
    assert ai_explain.explain_evidence_for_anomalies([]) == []
