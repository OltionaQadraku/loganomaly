from fastapi.testclient import TestClient

from api.main import app


def fresh_client():
    """An unauthenticated client, independent of the session-scoped
    logged-in `client` fixture other test files rely on."""
    return TestClient(app)


def test_register_creates_a_session():
    c = fresh_client()
    resp = c.post('/api/register', json={'username': 'alice', 'password': 'alicepass123'})
    assert resp.status_code == 200
    assert resp.json()['username'] == 'alice'
    assert c.get('/api/me').status_code == 200


def test_register_rejects_duplicate_username():
    c1 = fresh_client()
    c1.post('/api/register', json={'username': 'bob', 'password': 'bobpassword'})
    c2 = fresh_client()
    resp = c2.post('/api/register', json={'username': 'bob', 'password': 'anotherpass'})
    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'USERNAME_TAKEN'


def test_register_rejects_short_password():
    c = fresh_client()
    resp = c.post('/api/register', json={'username': 'shortpw', 'password': '123'})
    assert resp.status_code == 400
    assert resp.json()['detail']['reason'] == 'WEAK_PASSWORD'


def test_login_with_correct_credentials():
    c = fresh_client()
    c.post('/api/register', json={'username': 'carol', 'password': 'carolpass123'})
    c2 = fresh_client()
    resp = c2.post('/api/login', json={'username': 'carol', 'password': 'carolpass123'})
    assert resp.status_code == 200
    assert c2.get('/api/me').status_code == 200


def test_login_with_wrong_password_is_rejected():
    c = fresh_client()
    c.post('/api/register', json={'username': 'dave', 'password': 'davepass123'})
    c2 = fresh_client()
    resp = c2.post('/api/login', json={'username': 'dave', 'password': 'wrongpassword'})
    assert resp.status_code == 401
    assert resp.json()['detail']['reason'] == 'INVALID_CREDENTIALS'


def test_analyze_requires_authentication():
    c = fresh_client()
    resp = c.post('/api/analyze', files={'file': ('demo.log', b'not empty', 'text/plain')})
    assert resp.status_code == 401


def test_logout_clears_the_session():
    c = fresh_client()
    c.post('/api/register', json={'username': 'erin', 'password': 'erinpass123'})
    assert c.get('/api/me').status_code == 200
    c.post('/api/logout')
    assert c.get('/api/me').status_code == 401


def test_users_only_see_their_own_runs(valid_hdfs_text=None):
    hdfs_text = (
        '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
        'blk_-4542486744283261479 src: /10.251.30.179:33720 dest: /10.251.30.179:50010'
    )

    frank = fresh_client()
    frank.post('/api/register', json={'username': 'frank', 'password': 'frankpass123'})
    frank.post('/api/analyze', files={'file': ('frank.log', hdfs_text.encode(), 'text/plain')})

    grace = fresh_client()
    grace.post('/api/register', json={'username': 'grace', 'password': 'gracepass123'})

    frank_runs = frank.get('/api/runs').json()
    grace_runs = grace.get('/api/runs').json()

    assert len(frank_runs) >= 1
    assert grace_runs == []
    assert all(r['filename'] == 'frank.log' for r in frank_runs)


def test_user_cannot_fetch_another_users_run_by_id():
    henry = fresh_client()
    henry.post('/api/register', json={'username': 'henry', 'password': 'henrypass123'})
    hdfs_text = (
        '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
        'blk_-4542486744283261479 src: /10.251.30.179:33720 dest: /10.251.30.179:50010'
    )
    resp = henry.post('/api/analyze', files={'file': ('henry.log', hdfs_text.encode(), 'text/plain')})
    run_id = resp.json()['run_id']

    ivy = fresh_client()
    ivy.post('/api/register', json={'username': 'ivy', 'password': 'ivypassword'})
    assert ivy.get(f'/api/runs/{run_id}').status_code == 404
