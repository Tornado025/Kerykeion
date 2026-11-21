"""Email/password sessions and single-use SendGrid password-reset codes."""
import hashlib
import hmac
import logging
import os
import re
import secrets
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.db import connect

router = APIRouter(prefix='/api/auth', tags=['Authentication'])
log = logging.getLogger(__name__)
mail_log = logging.getLogger('uvicorn.error')
COOKIE = 'kerykeion_session'
SESSION_SECONDS = 12 * 60 * 60
RESET_MINUTES = 10
RESET_MESSAGE = 'If an account exists for that email, a reset code will be sent. The code expires in 10 minutes.'
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\Z")


def enabled():
    return os.getenv('AUTH_ENABLED', 'true').lower() not in ('0', 'false', 'no')


def normalize_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL.fullmatch(value):
        raise ValueError('Enter a valid email address.')
    return value


def password_hash(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)
    return f'scrypt$32768$8$1${salt.hex()}${key.hex()}'


def password_matches(password, encoded):
    try:
        method, n, r, p, salt, key = encoded.split('$')
        if (method, n, r, p) != ('scrypt', '32768', '8', '1'):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32, maxmem=128 * 1024 * 1024)
        return hmac.compare_digest(actual, bytes.fromhex(key))
    except (ValueError, TypeError):
        return False


DUMMY_HASH = password_hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def reset_mac(user_id, nonce, code):
    secret = os.getenv('AUTH_SECRET', '')
    if len(secret) < 32:
        raise HTTPException(503, 'Password reset is not configured. Contact the administrator.')
    return hmac.new(secret.encode(), f'{user_id}:{nonce}:{code}'.encode(), hashlib.sha256).hexdigest()


class EmailInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=254)

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        return normalize_email(value)


class Credentials(EmailInput):
    password: str = Field(min_length=1, max_length=128)


class NewAccount(Credentials):
    @field_validator('password')
    @classmethod
    def strong_password(cls, value):
        if len(value) < 9 or not all((any('A' <= c <= 'Z' for c in value), any('a' <= c <= 'z' for c in value), any('0' <= c <= '9' for c in value))):
            raise ValueError('Use 9–128 characters with an uppercase letter, a lowercase letter and a number.')
        return value


class ResetInput(NewAccount):
    code: str = Field(pattern=r'^\d{6}$')


def check_origin(request):
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return
    allowed = {x.strip().rstrip('/') for x in os.getenv('AUTH_ALLOWED_ORIGINS', 'http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:5173,http://localhost:5173').split(',') if x.strip()}
    origin = request.headers.get('origin')
    referer = request.headers.get('referer')
    if not origin and referer:
        parsed = urlsplit(referer)
        origin = f'{parsed.scheme}://{parsed.netloc}'
    if (origin and origin.rstrip('/') not in allowed) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'This request origin is not allowed.')


def public_user(row):
    return {'user_id': str(row['user_id']), 'email': row['email']}


def current_user(request):
    token = request.cookies.get(COOKIE, '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    with connect() as conn:
        row = conn.execute('''SELECT u.user_id,u.email FROM auth_session s JOIN app_user u USING(user_id)
            WHERE s.token_hash=%s AND s.expires_at>now() AND NOT u.disabled''', (digest(token),)).fetchone()
    return public_user(row) if row else None


def rate_limit(request, action, email, limit=10, seconds=900):
    # Do not trust X-Forwarded-For from arbitrary clients.
    ip = request.client.host if request.client else 'unknown'
    exceeded = False
    with connect() as conn:
        conn.execute('DELETE FROM auth_rate_limit WHERE expires_at<now()')
        for scope, maximum in ((f'email:{email}', limit), (f'ip:{ip}', max(30, limit * 5))):
            key = digest(f'{action}:{scope}')
            row = conn.execute('''INSERT INTO auth_rate_limit(bucket_key,hits,expires_at) VALUES(%s,1,now()+%s)
                ON CONFLICT(bucket_key) DO UPDATE SET hits=auth_rate_limit.hits+1 RETURNING hits''',
                (key, timedelta(seconds=seconds))).fetchone()
            exceeded = exceeded or row['hits'] > maximum
    if exceeded:
        raise HTTPException(429, 'Too many attempts. Please try again later.', headers={'Retry-After': str(seconds)})


def create_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    conn.execute('DELETE FROM auth_session WHERE expires_at<now()')
    conn.execute('INSERT INTO auth_session(token_hash,user_id,expires_at) VALUES(%s,%s,now()+%s)',
                 (digest(token), user_id, timedelta(seconds=SESSION_SECONDS)))
    return token


def set_cookie(response, token):
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=os.getenv('AUTH_COOKIE_SECURE', 'false').lower() == 'true', samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'


@router.get('/session')
def session(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return {'enabled': enabled(), 'user': current_user(request) if enabled() else None}


@router.post('/signup', status_code=201)
def signup(data: NewAccount, request: Request, response: Response):
    check_origin(request)
    rate_limit(request, 'signup', data.email, 5, 3600)
    encoded = password_hash(data.password)
    with connect() as conn:
        user = conn.execute('''INSERT INTO app_user(user_id,email,password_hash) VALUES(%s,%s,%s)
            ON CONFLICT(email) DO NOTHING RETURNING user_id,email''', (uuid.uuid4(), data.email, encoded)).fetchone()
        if user:
            token = create_session(conn, user['user_id'])
    if not user:
        raise HTTPException(409, 'Unable to create this account. Try signing in or resetting your password.')
    set_cookie(response, token)
    return {'user': public_user(user)}


@router.post('/login')
def login(data: Credentials, request: Request, response: Response):
    check_origin(request)
    rate_limit(request, 'login', data.email)
    with connect() as conn:
        user = conn.execute('SELECT * FROM app_user WHERE email=%s FOR UPDATE', (data.email,)).fetchone()
        valid = password_matches(data.password, user['password_hash'] if user else DUMMY_HASH)
        if valid and user and not user['disabled']:
            token = create_session(conn, user['user_id'])
        else:
            token = None
    if not token:
        raise HTTPException(401, 'Email or password is incorrect.')
    set_cookie(response, token)
    return {'user': public_user(user)}


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response):
    check_origin(request)
    with connect() as conn:
        conn.execute('DELETE FROM auth_session WHERE token_hash=%s', (digest(request.cookies.get(COOKIE, '')),))
    response.delete_cookie(COOKIE, path='/', httponly=True, samesite='lax', secure=os.getenv('AUTH_COOKIE_SECURE', 'false').lower() == 'true')
    response.headers['Cache-Control'] = 'no-store'


def send_reset_email(email, code):
    # Never include the API key, recipient or OTP in logs or exception messages.
    try:
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            result = client.post('https://api.sendgrid.com/v3/mail/send',
                headers={'Authorization': 'Bearer ' + os.environ['SENDGRID_API_KEY']},
                json={'personalizations': [{'to': [{'email': email}]}],
                      'from': {'email': os.environ['SENDGRID_FROM_EMAIL'], 'name': 'Kerykeion'},
                      'subject': 'Your Kerykeion password reset code',
                      'content': [{'type': 'text/plain', 'value': f'Your password reset code is {code}.\n\nIt expires in 10 minutes and can only be used once. If you did not request a password reset, you can ignore this email.'}],
                      'tracking_settings': {'click_tracking': {'enable': False}, 'open_tracking': {'enable': False}}})
        if result.status_code == 202:
            mail_log.info('SendGrid accepted password-reset email (HTTP 202, message_id=%s).',
                          result.headers.get('x-message-id', 'not provided'))
        else:
            # Record a closed diagnostic category; never log the provider body,
            # which can contain recipient addresses or other personal details.
            try:
                errors = ' '.join(str(e.get('message', '')) for e in result.json().get('errors', [])).lower()
            except (ValueError, AttributeError, TypeError):
                errors = ''
            reason = ('sender_not_verified' if 'verified sender' in errors else
                      'sending_limit' if 'credit' in errors or 'maximum' in errors else
                      'invalid_credentials' if result.status_code == 401 else
                      'rate_limited' if result.status_code == 429 else 'provider_rejected')
            mail_log.error('SendGrid rejected password-reset email (HTTP %s, reason=%s).', result.status_code, reason)
            raise RuntimeError('Email delivery unavailable')
    except httpx.HTTPError:
        mail_log.error('SendGrid password-reset request failed at the network/transport layer.')
        raise RuntimeError('Email delivery unavailable') from None
    except (KeyError, RuntimeError):
        raise RuntimeError('Email delivery unavailable') from None


def deliver_reset(user_id, nonce, email, code):
    try:
        send_reset_email(email, code)
    except RuntimeError:
        with connect() as conn:
            conn.execute('DELETE FROM password_reset WHERE user_id=%s AND nonce=%s', (user_id, nonce))
        log.error('Password-reset email delivery failed; pending code invalidated.')


@router.post('/forgot-password', status_code=202)
def forgot_password(data: EmailInput, request: Request, tasks: BackgroundTasks):
    check_origin(request)
    rate_limit(request, 'reset-send', data.email, 3, 900)
    rate_limit(request, 'reset-cooldown', data.email, 1, 60)
    if not os.getenv('SENDGRID_API_KEY') or not os.getenv('SENDGRID_FROM_EMAIL') or len(os.getenv('AUTH_SECRET', '')) < 32:
        raise HTTPException(503, 'Password reset email is not configured. Contact the administrator.')
    with connect() as conn:
        user = conn.execute('SELECT user_id FROM app_user WHERE email=%s AND NOT disabled FOR UPDATE', (data.email,)).fetchone()
        if user:
            code = f'{secrets.randbelow(1000000):06d}'
            nonce = secrets.token_urlsafe(24)
            mac = reset_mac(user['user_id'], nonce, code)
            conn.execute('''INSERT INTO password_reset(user_id,nonce,code_mac,expires_at) VALUES(%s,%s,%s,now()+interval '10 minutes')
                ON CONFLICT(user_id) DO UPDATE SET nonce=EXCLUDED.nonce,code_mac=EXCLUDED.code_mac,
                attempts=0,created_at=now(),expires_at=EXCLUDED.expires_at''', (user['user_id'], nonce, mac))
            tasks.add_task(deliver_reset, user['user_id'], nonce, data.email, code)
    return {'message': RESET_MESSAGE}


@router.post('/reset-password')
def reset_password(data: ResetInput, request: Request, response: Response):
    check_origin(request)
    rate_limit(request, 'reset-check', data.email, 10, 900)
    # Password derivation is performed for both existing and unknown accounts.
    encoded = password_hash(data.password)
    success = False
    with connect() as conn:
        user = conn.execute('SELECT user_id FROM app_user WHERE email=%s AND NOT disabled FOR UPDATE', (data.email,)).fetchone()
        row = conn.execute('SELECT *,expires_at>now() AS fresh FROM password_reset WHERE user_id=%s FOR UPDATE', (user['user_id'],)).fetchone() if user else None
        if row and row['fresh'] and row['attempts'] < 5:
            matches = hmac.compare_digest(row['code_mac'], reset_mac(user['user_id'], row['nonce'], data.code))
            if matches:
                conn.execute('UPDATE app_user SET password_hash=%s WHERE user_id=%s', (encoded, user['user_id']))
                conn.execute('DELETE FROM auth_session WHERE user_id=%s', (user['user_id'],))
                conn.execute('DELETE FROM password_reset WHERE user_id=%s', (user['user_id'],))
                success = True
            else:
                conn.execute('UPDATE password_reset SET attempts=attempts+1 WHERE user_id=%s', (user['user_id'],))
    # Raise after commit so invalid attempts cannot roll back their counter.
    if not success:
        raise HTTPException(400, 'The code is invalid or has expired. Request a new code.')
    response.delete_cookie(COOKIE, path='/', httponly=True, samesite='lax', secure=os.getenv('AUTH_COOKIE_SECURE', 'false').lower() == 'true')
    return {'message': 'Password updated. Sign in with your new password.'}
