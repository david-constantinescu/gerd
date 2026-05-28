"""Camera orientation for food preview."""

from __future__ import annotations

from PIL import Image

from upright.config import reload_tunables
from upright.hal.camera import orient_frame


def test_orient_frame_rotates_180_by_default(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    monkeypatch.setattr("upright.config.CONFIG_PATH", cfg)
    reload_tunables()

    img = Image.new("RGB", (4, 2), (255, 0, 0))
    img.putpixel((0, 0), (0, 255, 0))
    out = orient_frame(img)
    assert out.size == (4, 2)
    assert out.getpixel((3, 1)) == (0, 255, 0)


def test_orient_frame_disabled(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text('{"camera_rotate_180": false}')
    monkeypatch.setattr("upright.config.CONFIG_PATH", cfg)
    reload_tunables()

    img = Image.new("RGB", (2, 2), (10, 20, 30))
    assert orient_frame(img) is img
