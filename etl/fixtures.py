"""Explicitly synthetic integration fixtures; never presented as archive observations."""
def documents():
    variants=[dict(variant_id=i,gene_id=672 if i<110 else 675,variant_name=f'Synthetic test variant {i}',variant_type='fixture',chromosome='17',position=i,ref='A',alt='G') for i in range(100,120)]
    for rid in range(1,7):
        assertions=[];official={}
        for v in variants:
            i=v['variant_id'];cls='P' if (i+rid)%5==0 else 'V'
            for lab in ('A','B'):
                assertions.append(dict(scv_accession=f'SCVFIX{i}{lab}',variant_id=i,submitter_id=lab,submitter_name=f'Fixture lab {lab}',class_code=cls,review_status='criteria provided, single submitter',review_stars=1,date_evaluated=f'2024-{rid:02}-01',raw={'fixture':True}))
            official[str(i)]=cls
        yield dict(label=f'fixture-{rid:02}',release_date=f'2024-{rid:02}-01',provenance='synthetic_fixture',variants=variants,assertions=assertions,official=official,artifacts=[])
