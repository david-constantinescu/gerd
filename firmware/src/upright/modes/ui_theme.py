"""Layout helpers — draw at native panel size (no bitmap upscale)."""

from __future__ import annotations

from PIL import Image, ImageDraw

# Same palette as the pre-menu TFT build (high-contrast white on black).
_C_BG = (0, 0, 0)
_C_FG = (255, 255, 255)
_C_DIM = (180, 180, 180)
_C_ACCENT = (220, 220, 220)
_C_WARN = (180, 180, 180)
_C_OK = (220, 220, 220)


def new_frame(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (w, h), _C_BG)
    return img, ImageDraw.Draw(img)


def hr(d: ImageDraw.ImageDraw, y: int, w: int) -> None:
    d.line((4, y, w - 4, y), fill=_C_DIM)


def title_bar(d: ImageDraw.ImageDraw, title: str, w: int) -> None:
    d.text((4, 4), title[:22], fill=_C_FG)
    hr(d, 20, w)


def menu_row(
    d: ImageDraw.ImageDraw,
    y: int,
    label: str,
    *,
    w: int,
    selected: bool,
    row_h: int = 16,
) -> None:
    text = label if len(label) <= 24 else label[:23] + "."
    if selected:
        d.rectangle((4, y, w - 4, y + row_h - 1), fill=_C_FG)
        d.text((8, y + 2), text, fill=_C_BG)
    else:
        d.text((8, y + 2), text, fill=_C_FG)


def progress_bar(
    d: ImageDraw.ImageDraw, x: int, y: int, bar_w: int, bar_h: int, frac: float
) -> None:
    frac = max(0.0, min(1.0, frac))
    d.rectangle((x, y, x + bar_w, y + bar_h), outline=_C_FG)
    fill = int(bar_w * frac)
    if fill > 0:
        d.rectangle((x + 1, y + 1, x + fill, y + bar_h - 1), fill=_C_ACCENT)


def footer_hint(d: ImageDraw.ImageDraw, text: str, h: int) -> None:
    d.text((4, max(4, h - 22)), text[:28], fill=_C_DIM)


def battery_icon(
    d: ImageDraw.ImageDraw,
    x: int,
    y: int,
    pct: int,
    *,
    low: bool = False,
) -> None:
    """Horizontal battery: outline, level fill, centered ``NN%`` in black."""
    pct = max(0, min(100, int(pct)))
    outline = _C_WARN if low else _C_FG
    fill_col = _C_WARN if low else _C_ACCENT
    tip_w = 3
    body_w = 30
    body_h = 13
    body_right = x + body_w - tip_w

    # Body + positive terminal
    d.rectangle((x, y, body_right, y + body_h - 1), outline=outline)
    mid = y + body_h // 2
    d.rectangle((body_right + 1, mid - 2, x + body_w, mid + 1), fill=outline)

    # Inner cavity
    pad = 2
    ix = x + pad
    iy = y + pad
    inner_right = body_right - pad
    inner_bottom = y + body_h - pad - 1
    d.rectangle((ix, iy, inner_right, inner_bottom), fill=(24, 24, 24))

    # Charge level (left → right)
    inner_w = max(0, inner_right - ix)
    level_w = int(inner_w * pct / 100)
    if level_w > 0:
        d.rectangle((ix, iy, ix + level_w, inner_bottom), fill=fill_col)

    # Percent label on a small light chip so black text stays readable
    label = f"{pct}%"
    bbox = d.textbbox((0, 0), label)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = ix + max(0, (inner_w - tw) // 2)
    ty = iy + max(0, (inner_bottom - iy - th) // 2)
    chip_pad = 1
    d.rectangle(
        (tx - chip_pad, ty - chip_pad, tx + tw + chip_pad, ty + th + chip_pad),
        fill=(235, 235, 235),
    )
    d.text((tx, ty), label, fill=(0, 0, 0))
