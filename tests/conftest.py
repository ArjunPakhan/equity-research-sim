import shutil

import pytest

import data.fetch as fetch_module


@pytest.fixture(scope="session")
def _session_cache_dir(tmp_path_factory):
    # Copy of the real cache so fresh entries still hit; stale refetches land here, not in data/cache/.
    cache_dir = tmp_path_factory.mktemp("cache")
    for f in fetch_module.CACHE_DIR.glob("*.parquet"):
        shutil.copy2(f, cache_dir / f.name)
    return cache_dir


@pytest.fixture(autouse=True)
def _isolate_market_data_cache(monkeypatch, _session_cache_dir):
    monkeypatch.setattr(fetch_module, "CACHE_DIR", _session_cache_dir)
