import json
import os
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend import auth
from backend.app import app
from backend.db import connect, migrate

EMAIL = 'researcher@example.com'
PASSWORD = 'A long research password 7'
NEW_PASSWORD = 'A different long password 8'


def test_password_hashes_are_salted_and_verified():
    one, two = auth.password_hash(PASSWORD), auth.password_hash(PASSWORD)
    assert one != two and PASSWORD not in one
    assert auth.password_matches(PASSWORD, one)
    assert not auth.password_matches('wrong', one)
    assert not auth.password_matches(PASSWORD, 'invalid')


def test_signup_validates_email_and_password():
    with pytest.raises(ValueError):
        auth.NewAccount(email='bad address', password=PASSWORD)
    with pytest.raises(ValueError):
        auth.NewAccount(email=EMAIL, password='short')
    assert auth.NewAccount(email='  RESEARCHER@EXAMPLE.COM ', password=PASSWORD).email == EMAIL


def test_sendgrid_request_uses_verified_sender_and_no_tracking(monkeypatch):
    monkeypatch.setenv('SENDGRID_API_KEY', 'fake-key')
    monkeypatch.setenv('SENDGRID_FROM_EMAIL', 'verified@example.com')
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(202)
    original = httpx.Client
    monkeypatch.setattr(auth.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    auth.send_reset_email(EMAIL, '123456')
    body = json.loads(seen[0].content)
    assert seen[0].headers['authorization'] == 'Bearer fake-key'
    assert str(seen[0].url) == 'https://api.sendgrid.com/v3/mail/send'
    assert body['from']['email'] == 'verified@example.com'
    assert '123456' in body['content'][0]['value']
    assert body['tracking_settings']['open_tracking']['enable'] is False


def test_account_database_failure_fails_closed(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    def unavailable():
        raise psycopg.OperationalError('test database unavailable')
    monkeypatch.setattr(auth, 'connect', unavailable)
    with TestClient(app) as client:
        client.cookies.set(auth.COOKIE, 'a' * 43)
        result = client.get('/api/releases')
        assert result.status_code == 503
        assert 'test database unavailable' not in result.text
        assert result.headers['cache-control'] == 'no-store'


def test_mail_failure_logs_category_without_recipient_code_or_key(monkeypatch, caplog):
    monkeypatch.setenv('SENDGRID_API_KEY', 'secret-test-key')
    monkeypatch.setenv('SENDGRID_FROM_EMAIL', 'verified@example.com')
    original = httpx.Client
    def handler(request):
        return httpx.Response(403, json={'errors': [{'message': f'The from address does not match a verified Sender Identity. Recipient {EMAIL}'}]})
    monkeypatch.setattr(auth.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with caplog.at_level('INFO', logger='uvicorn.error'):
        with pytest.raises(RuntimeError, match='Email delivery unavailable'):
            auth.send_reset_email(EMAIL, '123456')
    assert 'HTTP 403' in caplog.text and 'sender_not_verified' in caplog.text
    assert all(value not in caplog.text for value in (EMAIL, '123456', 'secret-test-key'))


def test_accepted_mail_logs_provider_id_without_claiming_delivery(monkeypatch, caplog):
    monkeypatch.setenv('SENDGRID_API_KEY', 'secret-test-key')
    monkeypatch.setenv('SENDGRID_FROM_EMAIL', 'verified@example.com')
    original = httpx.Client
    monkeypatch.setattr(auth.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(lambda _: httpx.Response(202, headers={'x-message-id': 'test-message-id'})), **kw))
    with caplog.at_level('INFO', logger='uvicorn.error'):
        auth.send_reset_email(EMAIL, '123456')
    assert 'accepted' in caplog.text and 'test-message-id' in caplog.text
    assert all(value not in caplog.text for value in (EMAIL, '123456', 'secret-test-key', 'delivered'))


@pytest.fixture
def accounts(monkeypatch):
    if os.getenv('RUN_DB_TESTS') != '1':
        pytest.skip('Set RUN_DB_TESTS=1 for isolated PostgreSQL authentication tests')
    base = os.getenv('DATABASE_URL', 'postgresql://kerykeion:local-demo-only@localhost:55433/kerykeion')
    schema = 'test_auth_' + uuid.uuid4().hex
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    monkeypatch.setenv('DATABASE_URL', make_conninfo(base, options=f'-c search_path={schema}'))
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'false')
    monkeypatch.setenv('AUTH_SECRET', 'test-only-secret-' * 4)
    monkeypatch.setenv('SENDGRID_API_KEY', 'fake-key')
    monkeypatch.setenv('SENDGRID_FROM_EMAIL', 'verified@example.com')
    monkeypatch.setenv('AUTH_ALLOWED_ORIGINS', 'http://localhost:5173')
    sent = []
    monkeypatch.setattr(auth, 'send_reset_email', lambda email, code: sent.append((email, code)))
    migrate()
    try:
        with TestClient(app) as client:
            yield client, sent
    finally:
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def signup(client):
    result = client.post('/api/auth/signup', json={'email': EMAIL, 'password': PASSWORD})
    assert result.status_code == 201, result.text
    return result


def request_code(client, sent):
    result = client.post('/api/auth/forgot-password', json={'email': EMAIL})
    assert result.status_code == 202, result.text
    return sent[-1][1]


def test_signup_session_protected_api_and_logout(accounts, monkeypatch):
    client, _ = accounts
    monkeypatch.setattr('backend.services.releases', lambda: [])
    assert client.get('/api/releases').status_code == 401
    assert client.get('/openapi.json').status_code == 401
    result = signup(client)
    assert 'HttpOnly' in result.headers['set-cookie'] and 'SameSite=lax' in result.headers['set-cookie']
    token = client.cookies[auth.COOKIE]
    assert client.get('/api/auth/session').json()['user']['email'] == EMAIL
    assert client.get('/api/releases').status_code == 200
    assert client.get('/api/releases').headers['cache-control'] == 'no-store'
    with connect() as conn:
        row = conn.execute('SELECT * FROM auth_session').fetchone()
        assert row['token_hash'] == auth.digest(token) and row['token_hash'] != token
    assert client.post('/api/auth/logout').status_code == 204
    client.cookies.set(auth.COOKIE, token)
    assert client.get('/api/releases').status_code == 401


def test_login_uses_generic_errors_and_expires_sessions(accounts):
    client, _ = accounts
    signup(client)
    client.post('/api/auth/logout')
    wrong = client.post('/api/auth/login', json={'email': EMAIL, 'password': 'wrong'})
    unknown = client.post('/api/auth/login', json={'email': 'unknown@example.com', 'password': 'wrong'})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert client.post('/api/auth/login', json={'email': EMAIL, 'password': PASSWORD}).status_code == 200
    with connect() as conn:
        conn.execute("UPDATE auth_session SET expires_at=now()-interval '1 second'")
    assert client.get('/api/auth/session').json()['user'] is None
    assert client.get('/api/models').status_code == 401


def test_cross_origin_requests_are_rejected(accounts):
    client, _ = accounts
    signup(client)
    for path in ('/api/auth/logout', '/api/auth/forgot-password', '/api/projections/replay'):
        result = client.post(path, json={'email': EMAIL} if path.endswith('forgot-password') else {}, headers={'Origin': 'https://other.example'})
        assert result.status_code == 403
    assert client.get('/api/auth/session').json()['user']
    assert client.post('/api/auth/logout', headers={'Origin': 'http://localhost:5173'}).status_code == 204


def test_password_reset_is_single_use_and_revokes_every_session(accounts):
    client, sent = accounts
    signup(client)
    old_token = client.cookies[auth.COOKIE]
    with TestClient(app) as second:
        assert second.post('/api/auth/login', json={'email': EMAIL, 'password': PASSWORD}).status_code == 200
        code = request_code(client, sent)
        assert len(code) == 6
        with connect() as conn:
            row = conn.execute('SELECT * FROM password_reset').fetchone()
            assert row['code_mac'] != code
        assert client.post('/api/auth/reset-password', json={'email': EMAIL, 'code': code, 'password': NEW_PASSWORD}).status_code == 200
        assert second.get('/api/auth/session').json()['user'] is None
    client.cookies.set(auth.COOKIE, old_token)
    assert client.get('/api/models').status_code == 401
    assert client.post('/api/auth/reset-password', json={'email': EMAIL, 'code': code, 'password': PASSWORD}).status_code == 400
    assert client.post('/api/auth/login', json={'email': EMAIL, 'password': PASSWORD}).status_code == 401
    assert client.post('/api/auth/login', json={'email': EMAIL, 'password': NEW_PASSWORD}).status_code == 200


def test_wrong_code_attempts_persist_and_lock_out(accounts):
    client, sent = accounts
    signup(client)
    code = request_code(client, sent)
    wrong = '000000' if code != '000000' else '111111'
    for _ in range(5):
        assert client.post('/api/auth/reset-password', json={'email': EMAIL, 'code': wrong, 'password': NEW_PASSWORD}).status_code == 400
    with connect() as conn:
        assert conn.execute('SELECT attempts FROM password_reset').fetchone()['attempts'] == 5
    assert client.post('/api/auth/reset-password', json={'email': EMAIL, 'code': code, 'password': NEW_PASSWORD}).status_code == 400


def test_expired_code_cannot_change_password(accounts):
    client, sent = accounts
    signup(client)
    code = request_code(client, sent)
    with connect() as conn:
        conn.execute("UPDATE password_reset SET expires_at=now()-interval '1 second'")
    assert client.post('/api/auth/reset-password', json={'email': EMAIL, 'code': code, 'password': NEW_PASSWORD}).status_code == 400


def test_reset_does_not_disclose_account_existence(accounts):
    client, sent = accounts
    signup(client)
    known = client.post('/api/auth/forgot-password', json={'email': EMAIL})
    unknown = client.post('/api/auth/forgot-password', json={'email': 'unknown@example.com'})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(sent) == 1
    assert all(key not in known.text for key in ('code_mac', 'nonce', 'fake-key'))


def test_resend_cooldown_and_new_code_invalidates_old(accounts, monkeypatch):
    client, sent = accounts
    signup(client)
    values = iter([123456, 654321])
    monkeypatch.setattr(auth.secrets, 'randbelow', lambda _: next(values))
    old = request_code(client, sent)
    assert client.post('/api/auth/forgot-password', json={'email': EMAIL}).status_code == 429
    with connect() as conn:
        conn.execute('DELETE FROM auth_rate_limit')
    new = request_code(client, sent)
    assert old != new
    assert client.post('/api/auth/reset-password', json={'email': EMAIL, 'code': old, 'password': NEW_PASSWORD}).status_code == 400
    assert client.post('/api/auth/reset-password', json={'email': EMAIL, 'code': new, 'password': NEW_PASSWORD}).status_code == 200


def test_failed_email_invalidates_pending_code(accounts, monkeypatch):
    client, _ = accounts
    signup(client)
    def failed(*args):
        raise RuntimeError('Email delivery unavailable')
    monkeypatch.setattr(auth, 'send_reset_email', failed)
    assert client.post('/api/auth/forgot-password', json={'email': EMAIL}).status_code == 202
    with connect() as conn:
        assert conn.execute('SELECT count(*) n FROM password_reset').fetchone()['n'] == 0


def test_missing_sendgrid_config_blocks_reset_for_all_addresses(accounts, monkeypatch):
    client, sent = accounts
    signup(client)
    monkeypatch.delenv('SENDGRID_API_KEY')
    known = client.post('/api/auth/forgot-password', json={'email': EMAIL})
    unknown = client.post('/api/auth/forgot-password', json={'email': 'unknown@example.com'})
    assert known.status_code == unknown.status_code == 503
    assert known.json() == unknown.json()
    assert sent == []


def test_disabled_accounts_cannot_keep_or_create_sessions(accounts):
    client, sent = accounts
    signup(client)
    with connect() as conn:
        conn.execute('UPDATE app_user SET disabled=true WHERE email=%s', (EMAIL,))
    assert client.get('/api/auth/session').json()['user'] is None
    assert client.get('/api/releases').status_code == 401
    assert client.post('/api/auth/login', json={'email': EMAIL, 'password': PASSWORD}).status_code == 401
    assert client.post('/api/auth/forgot-password', json={'email': EMAIL}).status_code == 202
    assert sent == []


def test_login_rate_limit_is_persistent(accounts):
    client, _ = accounts
    for _ in range(10):
        assert client.post('/api/auth/login', json={'email': EMAIL, 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'email': EMAIL, 'password': 'wrong'}).status_code == 429


def test_https_cookies_are_secure(accounts, monkeypatch):
    monkeypatch.setenv('AUTH_COOKIE_SECURE', 'true')
    with TestClient(app, base_url='https://localhost') as client:
        assert 'Secure' in signup(client).headers['set-cookie']
        assert client.get('/api/auth/session').json()['user']

@pytest.mark.parametrize('password', ['Abcdefg1', 'abcdefgh1', 'ABCDEFGH1', 'Abcdefghi'])
def test_new_password_requires_length_and_each_character_class(password):
    with pytest.raises(ValueError):
        auth.NewAccount(email=EMAIL, password=password)


def test_nine_character_password_is_accepted_without_changing_login_rules():
    assert auth.NewAccount(email=EMAIL, password='Abcdefgh1').password == 'Abcdefgh1'
    assert auth.Credentials(email=EMAIL, password='existing lower case password').password
