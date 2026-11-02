export type Group = 'P'|'V'|'B'|'C'|'O';
export interface Release {release_id:number;release_date:string;label:string;manifest_sha256:string;provenance:'clinvar_archive'|'synthetic_fixture';imported_at:string;stats:{variants:number;assertions:number;matched:number;mismatched:number;duplicate_rows:number;rejected:number;policy:string}}
export interface Gene {gene_id:number;gene_symbol:string;description:string;variants:number;changed:number}
export interface Variant {variant_id:number;gene_id:number;gene_symbol:string;variant_name:string;variant_type:string;chromosome:string;position:number;ref:string;alt:string;description?:string;aggregate_class:Group;review_stars:number;submitter_count:number;assertion_count:number;change_type?:string;from_class?:Group;to_class?:Group}
export interface State {variant_id:number;release_id:number;aggregate_class:Group;review_stars:number;submitter_count:number;assertion_count:number;label:string}
export interface Assertion {scv_accession:string;submitter_id:string;submitter_name:string;version_no:number;class_code:Group;date_evaluated:string|null;first_release_id:number;last_release_id:number|null;status_label:string;review_stars:number}
export interface Event {event_id:number;variant_id:number;from_release_id:number;to_release_id:number;change_type:string;from_class:Group;to_class:Group;label:string;gene_symbol?:string;variant_name?:string}
export interface Prediction {prediction_id:number;model_id:number;variant_id:number;origin_release_id:number;horizon:number;score:number;audit_rank:number;realized_label:boolean|null;target_release_id:number|null;model_name?:string;feature_set?:string;variant_name?:string;gene_symbol?:string}
export interface MetricBudget {selected:number;observed:number;hits:number;recall:number|null;precision:number|null;unknown:number}
export interface Metrics {scored:number;evaluable:number;positives:number;coverage:number;average_precision:number|null;roc_auc:number|null;brier:number|null;budget_1:MetricBudget;budget_5:MetricBudget}
export interface Model {model_id:number;model_name:string;feature_set:string;origin_release_id:number;horizon:number;trained_on_release:number|null;run_key:string;metadata:Record<string,unknown>;label:string;metrics:Metrics|null}
export interface Detail {variant:Variant;release:Release;assertions:Assertion[];states:State[];events:Event[];predictions:Prediction[];validation:{official_class:Group;calculated_class:Group;matches:boolean}|null}
export interface Queue {model:Model|null;predictions:Prediction[];total:number;budget_count:number}
export interface Health {postgres:{status:string;releases?:number};mongodb:{status:string;evidence?:number};neo4j:{status:string};outbox?:{mongo_pending:number;neo4j_pending:number}}
export interface GraphRow {submitter:string;accession:string;version:number;classification:Group;first_release:number;last_release:number|null}
