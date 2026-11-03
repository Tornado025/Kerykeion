-- Archive TSVs lack stable organisation IDs. Record name-ID aliases supported
-- by unchanged SCV ownership, rather than splitting a renamed organisation.
CREATE TABLE submitter_alias (
    source_submitter_id text PRIMARY KEY,
    submitter_id text NOT NULL REFERENCES submitter(submitter_id),
    observed_name text NOT NULL,
    first_release_id integer NOT NULL REFERENCES release(release_id),
    evidence text NOT NULL
);
