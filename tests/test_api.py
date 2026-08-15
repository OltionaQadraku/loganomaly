from api.main import MAX_FILE_SIZE


def test_health_ok(client):
    resp = client.get('/api/health')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'ok'


def test_format_info(client):
    resp = client.get('/api/format-info')
    assert resp.status_code == 200
    body = resp.json()
    assert body['supported_format'] == 'HDFS'
    assert 'example_line' in body


def test_analyze_rejects_empty_file(client):
    resp = client.post('/api/analyze', files={'file': ('empty.log', b'', 'text/plain')})
    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'EMPTY_FILE'


def test_analyze_rejects_binary_file(client):
    resp = client.post('/api/analyze', files={
        'file': ('fake.log', b'\x00\x01\x02binary junk', 'text/plain'),
    })
    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'BINARY_FILE'


def test_analyze_rejects_blocked_extension(client):
    resp = client.post('/api/analyze', files={
        'file': ('archive.zip', b'PK\x03\x04 not really a log', 'application/zip'),
    })
    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'UNSUPPORTED_FILE_TYPE'


def test_analyze_rejects_oversized_file(client):
    oversized = b'0' * (MAX_FILE_SIZE + 1)
    resp = client.post('/api/analyze', files={'file': ('big.log', oversized, 'text/plain')})
    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'FILE_TOO_LARGE'


def test_analyze_reports_unrecognised_format_with_samples(client):
    resp = client.post('/api/analyze', files={
        'file': ('notes.log', b'# just some notes\nnothing log-shaped here\n', 'text/plain'),
    })
    assert resp.status_code == 400
    detail = resp.json()['detail']
    assert detail['reason'] == 'FORMAT_NOT_RECOGNISED'
    assert detail['sample_lines']


def test_analyze_accepts_valid_hdfs_file(client, valid_hdfs_text):
    resp = client.post('/api/analyze', files={
        'file': ('demo.log', valid_hdfs_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert 'message' in body
    assert body['warnings'] == []
    assert 'run_id' in body


def test_stats_endpoint_tracks_upload_failures(client):
    before = client.get('/api/stats').json()['upload_failures'].get('EMPTY_FILE', 0)
    client.post('/api/analyze', files={'file': ('empty.log', b'', 'text/plain')})
    after = client.get('/api/stats').json()['upload_failures'].get('EMPTY_FILE', 0)
    assert after == before + 1
