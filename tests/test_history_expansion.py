import pytest
from scripts.expand_history import months_between
from etl.transfer import download


def test_month_range_is_contiguous_across_years():
    assert months_between('2024-11','2025-02') == ['2024-11','2024-12','2025-01','2025-02']
    assert len(months_between('2023-01','2026-11')) == 47
    for start,end in [('2025-13','2026-01'),('2026-01','2025-01'),('2025-1','2025-02')]:
        with pytest.raises(ValueError):months_between(start,end)


def test_worker_limit_rejected_before_network(monkeypatch,tmp_path):
    monkeypatch.setenv('KERYKEION_DOWNLOAD_WORKERS','0')
    with pytest.raises(ValueError,match='workers'):
        download('https://example.invalid/archive.gz',tmp_path/'archive.gz')
