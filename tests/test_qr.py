"""Tests for app/qr.py — QR SVG generation."""
from __future__ import annotations

from app.qr import qr_svg


def test_qr_svg_returns_svg_string():
    result = qr_svg("SB-ABCD")
    assert "<svg" in result
    assert "</svg>" in result


def test_qr_svg_contains_no_newlines():
    result = qr_svg("SB-1234")
    assert "\n" not in result
    assert "\r" not in result


def test_qr_svg_custom_scale():
    small = qr_svg("SB-ABCD", scale=2)
    large = qr_svg("SB-ABCD", scale=8)
    assert "<svg" in small
    assert "<svg" in large
    assert len(large) > len(small)
