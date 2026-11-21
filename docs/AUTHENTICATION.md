# Authentication

Kerykeion uses email/password accounts, server-side sessions, and email OTPs for forgotten passwords. SendGrid delivers the email; the application creates, expires and checks the OTP. Twilio SMS Verify and phone numbers are not used.

## Setup

1. Run `.venv/bin/python -m backend.cli migrate` to create the four account-related tables. They do not change the ClinVar corpus.
2. Configure the ignored local `.env`:

   ```dotenv
   AUTH_ENABLED=true
   AUTH_SECRET=replace-with-a-random-secret-of-at-least-32-characters
   AUTH_COOKIE_SECURE=false
   AUTH_ALLOWED_ORIGINS=http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:5173,http://localhost:5173
   SENDGRID_API_KEY=your-sendgrid-api-key
   SENDGRID_FROM_EMAIL=your-verified-sender@example.com
   ```

   Generate the application secret once with `.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'`. The initial implementation created a random secret in the local `.env` if that file did not already exist; keep that value. The two SendGrid fields are intentionally blank until configured. Never put these settings in Vite variables or frontend code.
3. In SendGrid, create a Restricted Access API key with **Mail Send → Full Access**. Verify the sender email through Single Sender Verification or authenticate its domain. Set `SENDGRID_FROM_EMAIL` to an address covered by that verification.
4. Build the frontend with `npm --prefix frontend run build`, then restart the FastAPI process. The UI uses the same origin as the API, or Vite's existing `/api` proxy.
5. For a public HTTPS deployment, set `AUTH_COOKIE_SECURE=true` and list the exact public origins in `AUTH_ALLOWED_ORIGINS`. Configure proxy IP handling for the actual deployment rather than accepting arbitrary forwarded IP headers.

The optional `AUTH_ENABLED=false` setting bypasses the login requirement for a trusted local demo only. Authentication is enabled by default. Database failures fail closed. A missing SendGrid configuration disables password-reset requests with a setup message; signup and login remain available.

## User flow

- Create an account with an email address and a password of 9–128 characters containing an uppercase letter, a lowercase letter and a number; signup signs the user in. Signup does not separately verify email ownership.
- Sign in with email/password. A session lasts 12 hours and is stored in an HttpOnly, SameSite=Lax cookie. Session values are random opaque tokens; PostgreSQL stores only their SHA-256 hashes. The frontend does not use localStorage for authentication.
- Sign out to revoke the current session.
- Choose **Forgot password**, enter the account email, and request a six-digit code. Existing and unknown addresses receive the same acknowledgement. Only an existing active account receives an email.
- Enter the code and a new password. Codes expire in 10 minutes, permit at most five incorrect attempts, and can be used once. Resending replaces the previous code, with a 60-second cooldown and per-email/IP rate limits. Reset codes are stored as keyed HMACs, not plaintext.
- A successful reset revokes all sessions for that account and returns the user to sign in. Disabled accounts cannot log in or reset passwords.

Passwords use salted scrypt. Login and code requests are rate limited in PostgreSQL across workers. State-changing API requests reject unapproved browser origins; no wildcard CORS policy is installed. An API 401 clears the visible authenticated workspace.

The read APIs, CSV exports and API documentation require a session. `/api/health` remains public for local health checks. Projection replay requires both a signed-in session and the existing `WRITE_TOKEN`; accounts do not gain administrative privileges by signing up.

## Email and operations

SendGrid is called through its v3 Mail Send API with a 15-second timeout. Reset messages contain only the code and expiry; email tracking is disabled. API credentials and reset codes are not logged or returned to the browser. Email delivery runs after the response. A delivery failure invalidates the pending code and records a generic server error; inspect SendGrid activity for delivery to the mailbox. A 202 from SendGrid means accepted, not confirmed inbox delivery. The API server logs the HTTP status and SendGrid message ID for accepted requests, and a sanitized diagnostic category for rejections. It never logs the OTP, recipient address, API key, or raw provider error body. If a request is accepted but the email is missing, check Spam and the SendGrid Email Activity status (delivered, deferred, blocked, bounced, or dropped). A key restricted to Mail Send cannot read Email Activity; use the SendGrid console to inspect it.

Expired sessions and rate-limit buckets are removed during subsequent session creation or rate-limit requests. An expired reset row is unusable and is replaced by the next reset request. Account tables contain personal email addresses; backups and access permissions should include these new tables.

## Verification

```sh
RUN_DB_TESTS=1 .venv/bin/python -m pytest tests/test_auth.py -q
npm --prefix frontend run build
npm --prefix frontend test
```

Database integration tests create and drop temporary isolated schemas. SendGrid is mocked, so tests send no real email. A live delivery check requires your configured SendGrid key and sender, then a reset request for an account whose mailbox you control.

References: [SendGrid Mail Send API](https://www.twilio.com/docs/sendgrid/api-reference/mail-send/mail-send), [SendGrid API keys](https://www.twilio.com/docs/sendgrid/ui/account-and-settings/api-keys).
