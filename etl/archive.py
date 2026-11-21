"""Versioned, streamed ClinVar archive adapter. Never substitutes today's API data."""
import csv
import gzip
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
import requests
from backend.db import ROOT

GENES = {672: 'BRCA1', 675: 'BRCA2', 7157: 'TP53'}
ADAPTER_VERSION = 'germline-grch38-single-gene-v1'

def group(value):
    v = (value or '').strip().lower()
    if 'conflict' in v: return 'C'
    if 'pathogenic' in v and 'benign' not in v: return 'P'
    if 'benign' in v and 'pathogenic' not in v: return 'B'
    if 'uncertain' in v: return 'V'
    return 'O'

def stars(value):
    v = (value or '').lower()
    if 'practice guideline' in v: return 4
    if 'expert panel' in v: return 3
    if 'multiple submitters' in v and 'no conflicts' in v: return 2
    if 'criteria provided' in v and not v.startswith('no '): return 1
    return 0

def date_value(value):
    if not value or value.strip() in ('-', 'na', 'not provided'): return None
    for fmt in ('%b %d, %Y', '%Y-%m-%d', '%m/%d/%Y'):
        try: return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError: pass
    return None

def pick(row, *keys):
    for key in keys:
        value = row.get(key)
        if value and value not in ('-', 'na', 'not provided'): return value.strip()
    return ''

def archive_rows(path):
    # ClinVar evidence fields can exceed Python csv's default 128 KiB limit.
    # Keep the complete field; allow up to 64 MiB while retaining streaming rows.
    csv.field_size_limit(max(csv.field_size_limit(), 64 * 1024 * 1024))
    with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as f:
        # submission_summary begins with explanatory comments, not the tabular header.
        for line in f:
            fields=line.rstrip('\r\n').lstrip('#').split('\t')
            if 'VariationID' in fields and len(fields)>1:
                names=[n.strip() for n in fields]
                break
        else:raise ValueError('Archive has no VariationID tabular header')
        reader=csv.DictReader(f,fieldnames=names,delimiter='\t')
        for row in reader:
            if row.get('VariationID','').strip() and not row['VariationID'].startswith('#'):yield row

from etl.transfer import download

def fetch_month(month):
    if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', month): raise ValueError('Month must be YYYY-MM')
    destination = ROOT / 'data/extracts' / f'{month}.json.gz'
    if destination.exists():
        with gzip.open(destination, 'rt') as f: cached = json.load(f)
        if cached.get('adapter_version') != ADAPTER_VERSION: raise ValueError('Cached extract adapter differs; choose a new dataset')
        print(f'Using verified selected extract: {month}', flush=True); return destination
    cache = ROOT / 'data/cache'; cache.mkdir(parents=True, exist_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    artifacts = []; variants = {}; assertions = []; official = {}; headers = {}; rejected = 0
    for kind in ('variant_summary', 'submission_summary'):
        url = f'https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/{kind}_{month}.txt.gz'
        if int(month[:4]) < 2025: url = f'https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/archive/{month[:4]}/{kind}_{month}.txt.gz'
        path = cache / f'{kind}_{month}.txt.gz'
        print(f'Downloading {url}', flush=True)
        sha, size, modified = download(url, path)
        artifacts.append(dict(kind=kind,url=url,sha256=sha,bytes=size,last_modified=modified))
        for i, raw in enumerate(archive_rows(path)):
            if i == 0:
                headers[kind] = list(raw)
                print(f'{kind} fields: {list(raw)}', flush=True)
                needed = ('VariationID',) if kind == 'variant_summary' else ('VariationID',)
                if not all(k in raw for k in needed): raise ValueError('Required archive fields missing')
                if kind == 'submission_summary' and not any(k in raw for k in ('SCV', 'SCVAccession', 'SCVAccessionAndVersion')):
                    raise ValueError('Historical SCV accession unavailable; XML adapter required')
            try: vid = int(pick(raw,'VariationID'))
            except ValueError: continue
            if kind == 'variant_summary':
                if pick(raw,'Assembly') != 'GRCh38': continue
                gid = pick(raw,'GeneID')
                if not gid.isdigit() or int(gid) not in GENES: continue
                try: pos = int(pick(raw,'PositionVCF','Start'))
                except ValueError: rejected += 1; continue
                if pos < 0: rejected += 1; continue
                row = dict(variant_id=vid,gene_id=int(gid),variant_name=pick(raw,'Name') or f'Variation {vid}',variant_type=pick(raw,'Type'),chromosome=pick(raw,'Chromosome'),position=pos,ref=pick(raw,'ReferenceAlleleVCF','ReferenceAllele'),alt=pick(raw,'AlternateAlleleVCF','AlternateAllele'))
                if vid in variants and variants[vid] != row: raise ValueError(f'Ambiguous selected variant {vid}')
                variants[vid] = row
                official[vid] = group(pick(raw,'GermlineClassification','ClinicalSignificance'))
            elif vid in variants:
                # New archives separate classification channels; explicitly select germline.
                classification = pick(raw,'GermlineClassification','ClinicalSignificance')
                channel = pick(raw,'ClassificationType','ClassificationCategory')
                if channel and 'germline' not in channel.lower(): continue
                scv = pick(raw,'SCV','SCVAccession','SCVAccessionAndVersion').split('.')[0]
                name = pick(raw,'Submitter','SubmitterName')
                if not scv.startswith('SCV') or not name: rejected += 1; continue
                sid = pick(raw,'SubmitterID','SubmitterId') or 'name:'+hashlib.sha256(name.encode()).hexdigest()[:16]
                review = pick(raw,'ReviewStatus') or 'no assertion criteria provided'
                assertions.append(dict(scv_accession=scv,variant_id=vid,submitter_id=sid,submitter_name=name,class_code=group(classification),review_status=review,review_stars=stars(review),date_evaluated=date_value(pick(raw,'DateLastEvaluated','DateLastEvaluatedGermline')),raw=raw))
        print(f'{kind}: selected {len(variants)} variants / {len(assertions)} assertions', flush=True)
    if not variants or not assertions: raise ValueError('No selected historical records: inspect field mappings')
    from email.utils import parsedate_to_datetime
    source_date=parsedate_to_datetime(artifacts[0]['last_modified']).date().isoformat()
    if not source_date.startswith(month): raise ValueError('Source modification month differs from requested archive')
    doc=dict(label=month,release_date=source_date,provenance='clinvar_archive',adapter_version=ADAPTER_VERSION,variants=list(variants.values()),assertions=assertions,official=official,artifacts=artifacts,headers=headers,rejected=rejected)
    temp = destination.with_suffix('.tmp')
    with gzip.open(temp,'wt') as f: json.dump(doc,f,separators=(',',':'))
    temp.replace(destination)
    # Do not discard raw inputs until the complete selected extract is published.
    for kind in ('variant_summary','submission_summary'):
        path=cache/f'{kind}_{month}.txt.gz'
        path.unlink(missing_ok=True)
        path.with_suffix(path.suffix+'.ranges.json').unlink(missing_ok=True)
    return destination
