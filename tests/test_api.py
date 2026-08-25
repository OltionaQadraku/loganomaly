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
    assert 'HDFS' in detail['message']
    assert 'BGL' in detail['message']
    assert 'OpenSSH' in detail['message']
    assert 'Generic' in detail['message']
    assert detail['supported_formats']


def test_analyze_unrecognised_format_names_the_closest_guess(client):
    apache_lines = (
        b'127.0.0.1 - - [10/Oct/2023:13:55:36 +0000] "GET /index.html HTTP/1.1" 200 2326\n'
    )
    resp = client.post('/api/analyze', files={'file': ('access.log', apache_lines, 'text/plain')})
    assert resp.status_code == 400
    detail = resp.json()['detail']
    assert detail['guessed_format'] == 'apache'
    assert 'apache' in detail['message'].lower()


def test_analyze_accepts_valid_hdfs_file(client, valid_hdfs_text):
    resp = client.post('/api/analyze', files={
        'file': ('demo.log', valid_hdfs_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert 'message' in body
    assert body['warnings'] == []
    assert 'run_id' in body


def test_analyze_auto_detects_hdfs_without_log_type_param(client, valid_hdfs_text):
    resp = client.post('/api/analyze', files={
        'file': ('mystery.log', valid_hdfs_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    assert resp.json()['log_type'] == 'hdfs'


def test_analyze_auto_detects_bgl_without_log_type_param(client, valid_bgl_text):
    resp = client.post('/api/analyze', files={
        'file': ('mystery.log', valid_bgl_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    assert resp.json()['log_type'] == 'bgl'


def test_analyze_auto_detects_ssh_without_log_type_param(client, valid_ssh_text):
    resp = client.post('/api/analyze', files={
        'file': ('mystery.log', valid_ssh_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    assert resp.json()['log_type'] == 'ssh'


def test_analyze_auto_detects_generic_without_log_type_param(client, valid_generic_text):
    resp = client.post('/api/analyze', files={
        'file': ('mystery.log', valid_generic_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    assert resp.json()['log_type'] == 'generic'


def test_format_info_generic(client):
    resp = client.get('/api/format-info', params={'log_type': 'generic'})
    assert resp.status_code == 200
    assert resp.json()['supported_format'] == 'Generic/Application'


def test_stats_endpoint_tracks_upload_failures(client):
    before = client.get('/api/stats').json()['upload_failures'].get('EMPTY_FILE', 0)
    client.post('/api/analyze', files={'file': ('empty.log', b'', 'text/plain')})
    after = client.get('/api/stats').json()['upload_failures'].get('EMPTY_FILE', 0)
    assert after == before + 1


def test_health_reports_all_log_types(client):
    resp = client.get('/api/health')
    body = resp.json()
    assert set(body['log_types']) == {'hdfs', 'bgl', 'ssh', 'generic'}
    assert body['log_types']['bgl']['status'] == 'ok'
    assert body['log_types']['ssh']['status'] == 'ok'
    assert body['log_types']['generic']['status'] == 'ok'


def test_format_info_bgl(client):
    resp = client.get('/api/format-info', params={'log_type': 'bgl'})
    assert resp.status_code == 200
    assert resp.json()['supported_format'] == 'BGL'


def test_format_info_unknown_log_type(client):
    resp = client.get('/api/format-info', params={'log_type': 'nope'})
    assert resp.status_code == 400


def test_analyze_accepts_valid_bgl_file(client, valid_bgl_text):
    resp = client.post('/api/analyze', params={'log_type': 'bgl'}, files={
        'file': ('bgl.log', valid_bgl_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['log_type'] == 'bgl'
    assert 'message' in body


def test_analyze_rejects_unknown_log_type(client, valid_hdfs_text):
    resp = client.post('/api/analyze', params={'log_type': 'nope'}, files={
        'file': ('x.log', valid_hdfs_text.encode('utf-8'), 'text/plain'),
    })
    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'UNKNOWN_LOG_TYPE'


def test_templates_endpoint_bgl(client):
    resp = client.get('/api/templates', params={'log_type': 'bgl'})
    assert resp.status_code == 200
    assert len(resp.json()) > 0
