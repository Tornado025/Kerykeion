-- Application accounts are independent of the immutable ClinVar corpus.
CREATE TABLE app_user (
    user_id uuid PRIMARY KEY,
    email text NOT NULL UNIQUE CHECK (email = lower(email)),
    password_hash text NOT NULL,
    disabled boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE auth_session (
    token_hash text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES app_user ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX auth_session_user_idx ON auth_session(user_id);
CREATE INDEX auth_session_expiry_idx ON auth_session(expires_at);
CREATE TABLE password_reset (
    user_id uuid PRIMARY KEY REFERENCES app_user ON DELETE CASCADE,
    nonce text NOT NULL,
    code_mac text NOT NULL,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 5),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE TABLE auth_rate_limit (
    bucket_key text PRIMARY KEY,
    hits integer NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX auth_rate_expiry_idx ON auth_rate_limit(expires_at);
