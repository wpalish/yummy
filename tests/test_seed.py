"""Tests for app/seed.py — demo data seeding."""
from __future__ import annotations

from app.db import Store
from app.seed import PARTNERS, _BOXES, seed


def test_seed_populates_partners_and_boxes(tmp_path):
    s = Store(path=tmp_path / "seed.db")
    seed(s)
    partners = s.partners()
    assert len(partners) == len(PARTNERS)


def test_seed_creates_expected_number_of_boxes(tmp_path):
    s = Store(path=tmp_path / "seed.db")
    seed(s)
    total_boxes = sum(1 for p in PARTNERS for _ in s.partner_boxes(p.id))
    assert total_boxes == len(_BOXES)


def test_seed_boxes_are_available(tmp_path):
    s = Store(path=tmp_path / "seed.db")
    seed(s)
    boxes = s.boxes_available()
    assert len(boxes) == len(_BOXES)
    for b in boxes:
        assert b.qty_left > 0


def test_seed_is_idempotent(tmp_path):
    s = Store(path=tmp_path / "seed.db")
    seed(s)
    seed(s)
    p, b, o = s.count()
    assert p == len(PARTNERS)
    assert b == len(_BOXES)
