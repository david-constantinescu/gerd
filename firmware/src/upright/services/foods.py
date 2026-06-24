"""Food risk dictionary + (optional) TFLite inference.

Loads ``data/foods.json`` into memory. Each food has GERD risk tier, numeric
``gerd_score`` (0–100, higher = worse for reflux), and recommended upright hours.

When a TFLite model + ``.labels.txt`` are present (Food-101 class order),
:classify` maps camera frames → label → lookup. Without a model, classify()
returns None and the UI prompts manual follow-up.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import FOODS_PATH, TFLITE_MODEL_PATH, TUNABLES

log = logging.getLogger("services.foods")

VALID_RISKS = frozenset({"LOW", "MEDIUM", "HIGH"})

_DEFAULT_HOURS = {"LOW": 1.5, "MEDIUM": 2.25, "HIGH": 3.0}
_DEFAULT_SCORE = {"LOW": 22, "MEDIUM": 52, "HIGH": 84}

# Kept ASCII-only: the OLED uses PIL's built-in bitmap font, which renders an
# em dash (and accented letters) as a "tofu" box.
_ADVICE = {
    "LOW": "Low reflux risk",
    "MEDIUM": "Moderate reflux risk",
    "HIGH": "High reflux risk",
}

# GERD dietary guidance (well-documented reflux triggers vs reflux-friendly
# foods). Used to estimate a risk tier for any food the model recognizes that
# isn't in foods.json, so a recognized dish always yields useful advice.
_HIGH_RISK_KW = (
    "fried", "fries", "deep-fried", "tempura", "katsu", "schnitzel", "nugget",
    "pizza", "burger", "cheeseburger", "cheese", "nacho", "quesadilla",
    "bacon", "sausage", "salami", "pepperoni", "chorizo", "pancetta",
    "rib", "brisket", "wing", "fatty", "lard", "gravy", "butter", "cream",
    "alfredo", "carbonara", "poutine", "chocolate", "cocoa", "fudge",
    "brownie", "cake", "pie", "donut", "doughnut", "pastry", "croissant",
    "churro", "tart", "cheesecake", "ice cream", "custard", "caramel",
    "curry", "chili", "spicy", "jalapeno", "salsa", "ketchup", "bolognese",
    "tomato", "marinara", "citrus", "orange", "lemon", "lime", "grapefruit",
    "coffee", "espresso", "latte", "cappuccino", "mocha", "wine", "beer",
    "cocktail", "margarita", "whiskey", "vodka", "rum", "sangria", "mint",
    "peppermint", "onion", "garlic", "bbq", "barbecue", "taco", "burrito",
    "enchilada", "kebab", "hot dog",
)
_LOW_RISK_KW = (
    "oatmeal", "porridge", "rice", "quinoa", "couscous", "barley", "millet",
    "banana", "melon", "cantaloupe", "honeydew", "pear", "papaya", "lettuce",
    "spinach", "kale", "cucumber", "celery", "broccoli", "cauliflower",
    "carrot", "green bean", "pea", "zucchini", "asparagus", "boiled",
    "steamed", "grilled", "poached", "toast", "cracker", "pretzel",
    "rice cake", "tofu", "lentil", "chickpea", "edamame", "ginger", "fennel",
    "herbal tea", "chamomile", "yogurt", "oat milk", "almond milk", "apple",
    "berry", "blueberry", "strawberry", "raspberry",
)


@dataclass(frozen=True)
class FoodEntry:
    name: str
    risk: str  # LOW | MEDIUM | HIGH
    upright_hours: float
    gerd_score: int  # 0–100, higher = worse for GERD


@dataclass(frozen=True)
class FoodClassification:
    name: str
    risk: str
    confidence: float
    gerd_score: int
    upright_hours: float
    advice: str
    label: str  # raw model label


_DICT: dict[str, FoodEntry] = {}
_ALIASES: dict[str, str] = {}  # normalized alias → canonical key
_CURRENT_PATH: Path = FOODS_PATH


def _norm(key: str) -> str:
    return re.sub(r"\s+", " ", key.strip().lower())


def _register_alias(alias: str, canonical: str) -> None:
    a = _norm(alias)
    c = _norm(canonical)
    if a and a != c:
        _ALIASES[a] = c


def _parse_entry(name: str, raw: dict[str, Any]) -> FoodEntry:
    risk = str(raw.get("risk", "MEDIUM")).upper()
    if risk not in VALID_RISKS:
        risk = "MEDIUM"
    hours = float(raw.get("upright_hours", _DEFAULT_HOURS[risk]))
    score = int(raw.get("gerd_score", _DEFAULT_SCORE[risk]))
    score = max(0, min(100, score))
    return FoodEntry(name=name, risk=risk, upright_hours=hours, gerd_score=score)


def load(path: Path | None = None) -> dict[str, FoodEntry]:
    global _DICT, _ALIASES, _CURRENT_PATH
    p = path or FOODS_PATH
    _CURRENT_PATH = p
    _ALIASES.clear()
    _DICT = {}
    if not p.exists():
        log.warning("foods.json not found at %s", p)
        return _DICT
    raw = json.loads(p.read_text())
    for name, body in raw.items():
        if not isinstance(body, dict):
            continue
        entry = _parse_entry(name, body)
        key = _norm(name)
        _DICT[key] = entry
        _register_alias(name.replace(" ", "_"), name)
        for alias in body.get("aliases", []):
            if isinstance(alias, str):
                _register_alias(alias, name)
    log.info("loaded %d foods (%d aliases) from %s", len(_DICT), len(_ALIASES), p)
    return _DICT


def reload(path: Path | None = None) -> dict[str, FoodEntry]:
    """Reload dictionary from disk (e.g. after web API edit)."""
    global _interpreter, _input_details, _output_details, _labels, _zero_shot_pipeline
    # Reset *all* model state, not just the interpreter — leaving stale tensor
    # details/labels behind could mis-map outputs after a model swap.
    _interpreter = None
    _input_details = None
    _output_details = None
    _labels = []
    _zero_shot_pipeline = None
    return load(path)


def all_foods() -> dict[str, FoodEntry]:
    if not _DICT:
        load()
    return _DICT


def lookup(name: str) -> FoodEntry | None:
    if not _DICT:
        load()
    key = _norm(name)
    key = _ALIASES.get(key, key)
    hit = _DICT.get(key)
    if hit is not None:
        return hit
    # Try underscore ↔ space
    alt = key.replace("_", " ")
    if alt != key:
        alt = _ALIASES.get(alt, alt)
        return _DICT.get(alt)
    return None


def advice_for(entry: FoodEntry) -> str:
    # Upright hours are shown on their own line, so keep advice short + ASCII.
    return _ADVICE.get(entry.risk, "Stay upright after eating")


def upsert(
    name: str,
    risk: str,
    upright_hours: float,
    *,
    gerd_score: int | None = None,
    aliases: list[str] | None = None,
) -> None:
    if not _DICT:
        load()
    risk = risk.upper()
    if risk not in VALID_RISKS:
        risk = "MEDIUM"
    score = gerd_score if gerd_score is not None else _DEFAULT_SCORE[risk]
    entry = FoodEntry(
        name=name,
        risk=risk,
        upright_hours=upright_hours,
        gerd_score=max(0, min(100, int(score))),
    )
    _DICT[_norm(name)] = entry
    if aliases:
        for a in aliases:
            _register_alias(a, name)
    save()


def save(path: Path | None = None) -> None:
    p = path or _CURRENT_PATH
    serial: dict[str, dict[str, Any]] = {}
    for e in sorted(_DICT.values(), key=lambda x: x.name.lower()):
        serial[e.name] = {
            "risk": e.risk,
            "upright_hours": e.upright_hours,
            "gerd_score": e.gerd_score,
        }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(serial, indent=2, sort_keys=True))


# --------------------------------------------------------------------- TFLite

_interpreter = None
_input_details: list[Any] | None = None
_output_details: list[Any] | None = None
_labels: list[str] = []
_zero_shot_pipeline = None
_warned_no_model = False


def _load_interpreter_cls():
    """Return a TFLite ``Interpreter`` class from whichever runtime is present.

    ``ai-edge-litert`` is the maintained successor to ``tflite-runtime`` and is
    the only one with prebuilt wheels for modern macOS (used by the simulator)
    and recent Pythons; we still fall back to the classic names.
    """
    for mod, attr in (
        ("ai_edge_litert.interpreter", "Interpreter"),
        ("tflite_runtime.interpreter", "Interpreter"),
        ("tensorflow.lite", "Interpreter"),
    ):
        try:
            return getattr(__import__(mod, fromlist=[attr]), attr)
        except (ImportError, AttributeError):
            continue
    return None


def _ensure_model() -> bool:
    global _interpreter, _input_details, _output_details, _labels, _warned_no_model
    if _interpreter is not None:
        return True
    if not TFLITE_MODEL_PATH.exists():
        if not _warned_no_model:
            log.warning(
                "food model missing at %s — TFLite path disabled. "
                "Deploy a Food-101 quantized TFLite model (labels: %s) to enable it.",
                TFLITE_MODEL_PATH,
                TFLITE_MODEL_PATH.with_suffix(".labels.txt").name,
            )
            _warned_no_model = True
        return False
    Interpreter = _load_interpreter_cls()
    if Interpreter is None:
        log.warning(
            "no TFLite runtime — food vision disabled. "
            "Install one of: ai-edge-litert, tflite-runtime, tensorflow."
        )
        return False
    _interpreter = Interpreter(model_path=str(TFLITE_MODEL_PATH))
    _interpreter.allocate_tensors()
    _input_details = _interpreter.get_input_details()
    _output_details = _interpreter.get_output_details()
    label_path = TFLITE_MODEL_PATH.with_suffix(".labels.txt")
    if label_path.exists():
        _labels = [
            ln.strip()
            for ln in label_path.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        log.info("TFLite food model: %d labels", len(_labels))
    else:
        log.warning("missing %s — class names unknown", label_path)
    return True


def _label_at(idx: int) -> str:
    if idx < len(_labels):
        return _labels[idx]
    return f"class_{idx}"


def _risk_from_keywords(label: str) -> str:
    """Estimate a GERD risk tier from food-name keywords (trigger vs friendly)."""
    s = _norm(label)
    if any(kw in s for kw in _HIGH_RISK_KW):
        return "HIGH"
    if any(kw in s for kw in _LOW_RISK_KW):
        return "LOW"
    return "MEDIUM"


def _entry_named(label: str, src: FoodEntry | None) -> FoodEntry:
    """A FoodEntry that keeps the *detected* dish name but takes risk data from
    ``src`` if we matched a known food, else from keyword estimation."""
    if src is not None:
        return FoodEntry(
            name=label.strip(),
            risk=src.risk,
            upright_hours=src.upright_hours,
            gerd_score=src.gerd_score,
        )
    risk = _risk_from_keywords(label)
    return FoodEntry(
        name=label.strip(),
        risk=risk,
        upright_hours=_DEFAULT_HOURS[risk],
        gerd_score=_DEFAULT_SCORE[risk],
    )


def resolve_label(label: str) -> FoodEntry | None:
    """Map a model class name to a food entry.

    Order: the model's "not food" class is rejected; then exact name/alias,
    then a numeric-prefix strip, then the longest known food name appearing as
    a whole word in the label, and finally a keyword-based risk estimate so any
    recognized dish still produces useful advice. The returned entry always
    keeps the *detected* dish name for display.
    """
    if not _DICT:
        load()
    raw = label.strip()
    if _norm(raw) in ("", "background", "__background__"):
        return None

    hit = lookup(raw)
    if hit is not None:
        return hit  # exact/alias match — curated name is already correct

    cleaned = re.sub(r"^\d+\s+", "", raw)
    if cleaned != raw:
        hit = lookup(cleaned)
        if hit is not None:
            return hit

    # Longest known food name that appears as a whole word inside the label,
    # e.g. "New York-style pizza" -> "pizza", "Chicken fried steak" -> "steak".
    nl = _norm(raw)
    best_key: str | None = None
    for key in _DICT:
        if len(key) < 3:
            continue
        if re.search(rf"\b{re.escape(key)}\b", nl) and (
            best_key is None or len(key) > len(best_key)
        ):
            best_key = key
    if best_key is not None:
        return _entry_named(raw, _DICT[best_key])

    # Recognized food the dictionary doesn't list — estimate risk from keywords.
    return _entry_named(raw, None)


def _have_memory_for_clip(min_gb: float = 2.0) -> bool:
    """CLIP-ViT-Large needs gigabytes of RAM — never attempt it on a Pi Zero 2 W
    (512 MB) where it would OOM/hang the food-photo flow. Skip unless the host
    has enough memory (or the operator forces it on)."""
    if os.environ.get("UPRIGHT_FORCE_CLIP") == "1":
        return True
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        return total >= min_gb * (1024**3)
    except (ValueError, OSError, AttributeError):
        return False


def _ensure_zero_shot_pipeline():
    global _zero_shot_pipeline
    if _zero_shot_pipeline is not None:
        return _zero_shot_pipeline
    if not _have_memory_for_clip():
        log.info("skipping CLIP zero-shot classifier — insufficient RAM for this device")
        return None
    try:
        from transformers import pipeline  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        _zero_shot_pipeline = pipeline(
            "zero-shot-image-classification",
            model="openai/clip-vit-large-patch14",
        )
    except Exception as exc:  # pragma: no cover - dependency/runtime specific
        log.warning("zero-shot food classifier unavailable: %s", exc)
        _zero_shot_pipeline = None
    return _zero_shot_pipeline


def _zero_shot_candidate_labels() -> list[str]:
    if not _DICT:
        load()
    labels = sorted({e.name.strip().lower() for e in _DICT.values() if e.name.strip()})
    return labels


def _classify_with_zero_shot(image) -> FoodClassification | None:
    zsc = _ensure_zero_shot_pipeline()
    if zsc is None:
        return None
    candidate_labels = _zero_shot_candidate_labels()
    if not candidate_labels:
        return None
    min_conf = float(TUNABLES.food_min_confidence)
    try:
        preds = zsc(images=image, candidate_labels=candidate_labels)
    except Exception as exc:  # pragma: no cover - model/runtime specific
        log.warning("zero-shot food classifier failed: %s", exc)
        return None
    for row in preds:
        label = str(row.get("label", "")).strip()
        confidence = float(row.get("score", 0.0))
        if confidence < min_conf:
            continue
        entry = resolve_label(label)
        if entry is not None:
            return FoodClassification(
                name=entry.name,
                risk=entry.risk,
                confidence=confidence,
                gerd_score=entry.gerd_score,
                upright_hours=entry.upright_hours,
                advice=advice_for(entry),
                label=label,
            )
    return None


def _scores_to_probs(flat):
    """Turn model outputs into a probability vector.

    The bundled AIY Food model emits quantized scores that dequantize to values
    in [0, 1]. When they already sum to ~1 they are probabilities; otherwise
    they are unnormalized masses that should be divided by their sum (not
    softmaxed across 2000+ near-zero classes, and not divided by 255 again).
    Float logits (max > 1.5 or negative values) still get a softmax.
    """
    import numpy as np

    flat = np.asarray(flat, dtype=np.float32).reshape(-1)
    total = float(flat.sum())
    if flat.min() >= 0 and flat.max() <= 1.0 and abs(total - 1.0) < 0.05:
        return flat
    if flat.min() < 0 or flat.max() > 1.5:
        x = flat - flat.max()
        exp = np.exp(x)
        return exp / exp.sum()
    return flat / total if total > 0 else flat


def _classify_tflite(image) -> FoodClassification | None:
    """Run the bundled TFLite Food-101 model (primary path on Pi + simulator)."""
    if not _ensure_model():
        return None

    import numpy as np

    inp = _input_details[0]  # type: ignore[index]
    h, w = int(inp["shape"][1]), int(inp["shape"][2])
    img = image.resize((w, h)).convert("RGB")
    arr = np.asarray(img, dtype=np.uint8)
    if inp["dtype"] != np.uint8:
        arr = (arr.astype(np.float32) / 127.5) - 1.0
    batch = np.expand_dims(arr, 0)
    _interpreter.set_tensor(inp["index"], batch)  # type: ignore[union-attr]
    _interpreter.invoke()  # type: ignore[union-attr]
    out_detail = _output_details[0]  # type: ignore[index]
    out = _interpreter.get_tensor(out_detail["index"])[0]  # type: ignore[union-attr]

    raw = np.asarray(out).reshape(-1)
    if raw.dtype in (np.uint8, np.int8):
        q = out_detail.get("quantization") if hasattr(out_detail, "get") else None
        if isinstance(q, (tuple, list)) and len(q) == 2 and float(q[0]):
            raw = (raw.astype(np.float32) - int(q[1])) * float(q[0])
        else:
            raw = raw.astype(np.float32) / 255.0

    probs = _scores_to_probs(raw)
    min_conf = float(TUNABLES.food_min_confidence)
    for idx in np.argsort(probs)[::-1][:12]:
        idx = int(idx)
        confidence = float(probs[idx])
        if confidence < min_conf:
            continue
        label = _label_at(idx)
        entry = resolve_label(label)
        if entry is not None:
            return FoodClassification(
                name=entry.name,
                risk=entry.risk,
                confidence=confidence,
                gerd_score=entry.gerd_score,
                upright_hours=entry.upright_hours,
                advice=advice_for(entry),
                label=label,
            )

    log.info("food classify: no mapped label above %.0f%% confidence", min_conf * 100)
    return None


def classify(image) -> FoodClassification | None:
    """Returns classification or None if no model / low confidence / no image."""
    if image is None:
        return None
    if not _DICT:
        load()
    result = _classify_tflite(image)
    if result is not None:
        return result
    return _classify_with_zero_shot(image)
