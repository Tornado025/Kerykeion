-- A distinct target: first observed future interpretation-group change.
-- Keep earlier endpoint-change experiments intact and separately labelled.
CREATE TABLE timing_run (
 run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_key text NOT NULL UNIQUE,
 origin_release_id integer NOT NULL REFERENCES release,
 method text NOT NULL,
 max_months integer NOT NULL CHECK(max_months=6),
 metadata jsonb NOT NULL,
 metrics jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE timing_forecast (
 run_id bigint NOT NULL REFERENCES timing_run,
 variant_id bigint NOT NULL REFERENCES variant,
 event_probabilities jsonb NOT NULL,
 cumulative_probabilities jsonb NOT NULL,
 expected_month_if_change double precision,
 median_month integer CHECK(median_month BETWEEN 1 AND 6),
 priority_rank integer NOT NULL CHECK(priority_rank>0),
 PRIMARY KEY(run_id,variant_id),
 UNIQUE(run_id,priority_rank)
);
CREATE INDEX timing_run_origin_idx ON timing_run(origin_release_id DESC,run_id DESC);
