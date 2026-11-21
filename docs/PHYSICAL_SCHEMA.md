# Implemented relational schema

The approved conceptual ER is retained in docs/deliverables. This inventory includes the physical support tables and read views used by the implementation.


## assertion_version

| Column | Type | Nullable |
|---|---|---|
| scv_accession | text | NO |
| version_no | integer | NO |
| class_code | text | NO |
| status_code | text | NO |
| date_evaluated | date | YES |
| first_release_id | integer | NO |
| last_release_id | integer | YES |
| content_hash | text | NO |
| raw | jsonb | NO |

## benchmark_result

| Column | Type | Nullable |
|---|---|---|
| model_id | bigint | NO |
| metrics | jsonb | NO |
| created_at | timestamp with time zone | NO |

## change_event

| Column | Type | Nullable |
|---|---|---|
| event_id | bigint | NO |
| variant_id | bigint | NO |
| from_release_id | integer | NO |
| to_release_id | integer | NO |
| change_type | text | NO |

## class_conflict_rule

| Column | Type | Nullable |
|---|---|---|
| class_code | text | YES |
| is_conflicting | boolean | YES |

## classification_term

| Column | Type | Nullable |
|---|---|---|
| class_code | text | NO |
| label | text | NO |

## clinical_assertion

| Column | Type | Nullable |
|---|---|---|
| scv_accession | text | NO |
| variant_id | bigint | NO |
| submitter_id | text | NO |
| first_release_id | integer | NO |

## drift_prediction

| Column | Type | Nullable |
|---|---|---|
| prediction_id | bigint | NO |
| model_id | bigint | NO |
| variant_id | bigint | NO |
| origin_release_id | integer | NO |
| horizon | integer | NO |
| score | double precision | NO |
| audit_rank | integer | NO |

## event_details

| Column | Type | Nullable |
|---|---|---|
| event_id | bigint | YES |
| variant_id | bigint | YES |
| from_release_id | integer | YES |
| to_release_id | integer | YES |
| change_type | text | YES |
| from_class | text | YES |
| to_class | text | YES |

## feature_materialization

| Column | Type | Nullable |
|---|---|---|
| variant_id | bigint | NO |
| origin_release_id | integer | NO |
| feature_set | text | NO |
| features | jsonb | NO |
| lineage_max_release | integer | NO |
| feature_hash | text | NO |

## gene

| Column | Type | Nullable |
|---|---|---|
| gene_id | integer | NO |
| gene_symbol | text | NO |
| description | text | NO |

## model_version

| Column | Type | Nullable |
|---|---|---|
| model_id | bigint | NO |
| model_name | text | NO |
| feature_set | text | NO |
| origin_release_id | integer | NO |
| horizon | integer | NO |
| trained_on_release | integer | YES |
| run_key | text | NO |
| metadata | jsonb | NO |
| created_at | timestamp with time zone | NO |

## outbox_event

| Column | Type | Nullable |
|---|---|---|
| event_id | bigint | NO |
| event_key | text | NO |
| topic | text | NO |
| payload | jsonb | NO |
| created_at | timestamp with time zone | NO |
| delivered_mongo | boolean | NO |
| delivered_neo4j | boolean | NO |
| attempts | integer | NO |
| last_error | text | YES |

## prediction_outcome

| Column | Type | Nullable |
|---|---|---|
| variant_id | bigint | NO |
| origin_release_id | integer | NO |
| horizon | integer | NO |
| target_release_id | integer | YES |
| realized_label | boolean | NO |

## prediction_results

| Column | Type | Nullable |
|---|---|---|
| prediction_id | bigint | YES |
| model_id | bigint | YES |
| variant_id | bigint | YES |
| origin_release_id | integer | YES |
| horizon | integer | YES |
| score | double precision | YES |
| audit_rank | integer | YES |
| realized_label | boolean | YES |
| target_release_id | integer | YES |

## release

| Column | Type | Nullable |
|---|---|---|
| release_id | integer | NO |
| release_date | date | NO |
| label | text | NO |
| manifest_sha256 | text | NO |
| provenance | text | NO |
| imported_at | timestamp with time zone | NO |
| stats | jsonb | NO |

## release_artifact

| Column | Type | Nullable |
|---|---|---|
| release_id | integer | NO |
| kind | text | NO |
| url | text | YES |
| sha256 | text | YES |
| bytes | bigint | YES |

## review_status

| Column | Type | Nullable |
|---|---|---|
| status_code | text | NO |
| status_label | text | NO |
| review_stars | integer | NO |

## schema_migration

| Column | Type | Nullable |
|---|---|---|
| name | text | NO |
| applied_at | timestamp with time zone | YES |

## submitter

| Column | Type | Nullable |
|---|---|---|
| submitter_id | text | NO |
| submitter_name | text | NO |
| organization_type | text | YES |

## submitter_alias

| Column | Type | Nullable |
|---|---|---|
| source_submitter_id | text | NO |
| submitter_id | text | NO |
| observed_name | text | NO |
| first_release_id | integer | NO |
| evidence | text | NO |

## validation_result

| Column | Type | Nullable |
|---|---|---|
| variant_id | bigint | NO |
| release_id | integer | NO |
| official_class | text | YES |
| calculated_class | text | YES |
| matches | boolean | YES |

## variant

| Column | Type | Nullable |
|---|---|---|
| variant_id | bigint | NO |
| gene_id | integer | NO |
| variant_name | text | NO |
| variant_type | text | YES |
| chromosome | text | YES |
| position | bigint | YES |
| ref | text | YES |
| alt | text | YES |

## variant_state

| Column | Type | Nullable |
|---|---|---|
| variant_id | bigint | NO |
| release_id | integer | NO |
| aggregate_class | text | YES |
| review_stars | integer | NO |
| submitter_count | integer | NO |
| assertion_count | integer | NO |
| n_p | integer | NO |
| n_vus | integer | NO |
| n_b | integer | NO |
