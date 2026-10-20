"""Pixabay fetch, cache, fallback — all offline (mock requests)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import skia

from whatif import load_config
from whatif.render import photos


class _FakeResp:
    def __init__(self, status: int, payload: dict, content: bytes = b""):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def cfg(tmp_path):
    c = load_config()
    c["photos"]["cache_dir"] = str(tmp_path / "cache")
    return c


def test_missing_key_falls_back(monkeypatch, cfg, tmp_path):
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    res = photos.fetch_photo("bees", cfg, tmp_path / "cache")
    assert res is None


def test_api_failure_falls_back(monkeypatch, cfg, tmp_path):
    monkeypatch.setenv("PIXABAY_API_KEY", "dummy")

    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(photos.requests, "get", boom)
    res = photos.fetch_photo("bees", cfg, tmp_path / "cache")
    assert res is None


def test_zero_results_falls_back(monkeypatch, cfg, tmp_path):
    monkeypatch.setenv("PIXABAY_API_KEY", "dummy")
    monkeypatch.setattr(photos.requests, "get",
                        lambda *a, **k: _FakeResp(200, {"hits": []}))
    assert photos.fetch_photo("nonsense_zzz", cfg, tmp_path / "cache") is None


def test_successful_fetch_and_cache_hit_makes_no_call(monkeypatch, cfg, tmp_path):
    monkeypatch.setenv("PIXABAY_API_KEY", "dummy")
    hits = {"hits": [{"imageWidth": 1000, "largeImageURL": "https://x.test/a.jpg",
                      "user": "alice", "pageURL": "https://x.test/p"}]}

    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None, **k):
        calls["n"] += 1
        if "pixabay.com/api" in url:
            return _FakeResp(200, hits)
        # image download
        surface = skia.Surface(64, 64)
        surface.getCanvas().clear(skia.Color(200, 100, 50))
        data = surface.makeImageSnapshot().encodeToData()
        r = _FakeResp(200, {})
        r.content = bytes(data)
        return r

    monkeypatch.setattr(photos.requests, "get", fake_get)
    cache = tmp_path / "cache"
    res = photos.fetch_photo("bees", cfg, cache)
    assert res is not None
    assert res.user == "alice"
    assert res.page_url == "https://x.test/p"
    first_calls = calls["n"]

    res2 = photos.fetch_photo("bees", cfg, cache)
    assert res2.cached is True
    assert calls["n"] == first_calls, "cache hit must not call network"


def test_center_crop_square_produces_square():
    surface = skia.Surface(200, 100)
    surface.getCanvas().clear(skia.Color(10, 20, 30))
    img = surface.makeImageSnapshot()
    sq = photos.center_crop_square(img)
    assert sq.width() == sq.height() == 100


def test_draw_card_renders_non_empty_from_in_memory_image(cfg):
    surface_src = skia.Surface(256, 256)
    surface_src.getCanvas().clear(skia.Color(255, 0, 0))
    img = surface_src.makeImageSnapshot()

    surface = skia.Surface(720, 720)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorBLACK)
    photos.draw_card(canvas, cfg, img, 360, 360, 520, 12, t=1.0, popin_t0=0.0)
    arr = surface.makeImageSnapshot().toarray()
    assert (arr[:, :, :3].sum(axis=2) > 0).any()