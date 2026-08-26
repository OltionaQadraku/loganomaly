import json
from unittest.mock import MagicMock, patch

import src.ai_explain as ai_explain


def _reset_ai_client_cache():
    ai_explain._client = None
    ai_explain._client_checked = False


def _fake_completion(text):
    message = MagicMock(content=text)
    choice = MagicMock(message=message)
    return MagicMock(choices=[choice])


def _analyze_generic_run(client, valid_generic_text):
    resp = client.post('/api/analyze', files={
        'file': ('mystery.log', valid_generic_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['anomalies_found'] > 0
    return body['run_id'], body['anomalies'][0]['session_id']


def test_explain_endpoint_returns_400_when_ai_not_configured(client, valid_generic_text, monkeypatch):
    _reset_ai_client_cache()
    monkeypatch.delenv('GROQ_API_KEY', raising=False)

    run_id, session_id = _analyze_generic_run(client, valid_generic_text)
    resp = client.post(f'/api/runs/{run_id}/anomalies/{session_id}/explain')

    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'AI_NOT_CONFIGURED'


def test_explain_endpoint_enhances_and_caches_the_report(client, valid_generic_text, monkeypatch):
    _reset_ai_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    run_id, session_id = _analyze_generic_run(client, valid_generic_text)

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_completion(json.dumps({
        '0': 'The database service specifically refused new connections.',
    }))

    with patch('groq.Groq', return_value=fake_client):
        resp = client.post(f'/api/runs/{run_id}/anomalies/{session_id}/explain')

    assert resp.status_code == 200
    body = resp.json()
    assert 'The database service specifically refused new connections.' in body['report']

    resp2 = client.get(f'/api/runs/{run_id}/anomalies/{session_id}')
    assert resp2.status_code == 200
    assert 'The database service specifically refused new connections.' in resp2.json()['report']

    _reset_ai_client_cache()


def test_explain_endpoint_404_for_unknown_session(client, valid_generic_text, monkeypatch):
    _reset_ai_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    run_id, _ = _analyze_generic_run(client, valid_generic_text)
    resp = client.post(f'/api/runs/{run_id}/anomalies/window-999999/explain')

    assert resp.status_code == 404
    _reset_ai_client_cache()


def test_explain_endpoint_502_when_ai_call_fails(client, valid_generic_text, monkeypatch):
    _reset_ai_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    run_id, session_id = _analyze_generic_run(client, valid_generic_text)

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = Exception('network error')

    with patch('groq.Groq', return_value=fake_client):
        resp = client.post(f'/api/runs/{run_id}/anomalies/{session_id}/explain')

    assert resp.status_code == 502
    assert resp.json()['detail']['reason'] == 'AI_CALL_FAILED'
    _reset_ai_client_cache()


def test_explain_endpoint_not_supported_for_hdfs(client, valid_hdfs_text, monkeypatch):
    _reset_ai_client_cache()
    monkeypatch.setenv('GROQ_API_KEY', 'test-key')

    resp = client.post('/api/analyze', files={
        'file': ('mystery.log', valid_hdfs_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    body = resp.json()
    run_id = body['run_id']
    session_id = body['anomalies'][0]['session_id'] if body['anomalies'] else None
    assert session_id, "expected the HDFS fixture to produce at least one anomaly"

    resp2 = client.post(f'/api/runs/{run_id}/anomalies/{session_id}/explain')
    assert resp2.status_code == 400
    assert resp2.json()['detail']['reason'] == 'NOT_SUPPORTED'
    _reset_ai_client_cache()
