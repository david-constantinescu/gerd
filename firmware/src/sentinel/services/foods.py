"""Food risk dictionary + (optional) TFLite inference.

Loads ``data/foods.json`` into memory at startup. The webapp can edit it
through the API and call :func:`reload`. If a TFLite model is present we run
MobileNetV2 inference; otherwise classify() returns ``None`` and the user is
prompted to enter the food manually on the OLED.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import FOODS_PATH, TFLITE_MODEL_PATH, TUNABLES

log = logging.getLogger("services.foods")


@dataclass
class FoodEntry:
    name: str
    risk: str  # LOW | MEDIUM | HIGH
    upright_hours: float


_DICT: dict[str, FoodEntry] = {}
_CURRENT_PATH: Path = FOODS_PATH


def load(path: Path | None = None) -> dict[str, FoodEntry]:
    global _DICT, _CURRENT_PATH
    p = path or FOODS_PATH
    _CURRENT_PATH = p
    if not p.exists():
        log.warning("foods.json not found at %s", p)
        _DICT = {}
        return _DICT
    raw = json.loads(p.read_text())
    _DICT = {
        k.lower(): FoodEntry(name=k, risk=v["risk"], upright_hours=v["upright_hours"])
        for k, v in raw.items()
    }
    log.info("loaded %d foods from %s", len(_DICT), p)
    return _DICT


def all_foods() -> dict[str, FoodEntry]:
    if not _DICT:
        load()
    return _DICT


def lookup(name: str) -> FoodEntry | None:
    if not _DICT:
        load()
    return _DICT.get(name.lower())


def upsert(name: str, risk: str, upright_hours: float) -> None:
    if not _DICT:
        load()
    _DICT[name.lower()] = FoodEntry(name=name, risk=risk, upright_hours=upright_hours)
    save()


def save(path: Path | None = None) -> None:
    p = path or _CURRENT_PATH
    serial = {e.name: {"risk": e.risk, "upright_hours": e.upright_hours} for e in _DICT.values()}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(serial, indent=2, sort_keys=True))


# --------------------------------------------------------------------- TFLite

_interpreter = None
_input_details: list[Any] | None = None
_output_details: list[Any] | None = None
_labels: list[str] = []


def _ensure_model() -> bool:
    global _interpreter, _input_details, _output_details, _labels
    if _interpreter is not None:
        return True
    if not TFLITE_MODEL_PATH.exists():
        return False
    try:
        from tflite_runtime.interpreter import Interpreter  # type: ignore[import-not-found]
    except ImportError:
        try:
            from tensorflow.lite import Interpreter  # type: ignore[import-not-found]
        except ImportError:
            log.warning("no tflite runtime — food vision disabled")
            return False
    _interpreter = Interpreter(model_path=str(TFLITE_MODEL_PATH))
    _interpreter.allocate_tensors()
    _input_details = _interpreter.get_input_details()
    _output_details = _interpreter.get_output_details()
    label_path = TFLITE_MODEL_PATH.with_suffix(".labels.txt")
    if label_path.exists():
        _labels = label_path.read_text().splitlines()
    return True


def classify(image) -> tuple[str, str, float] | None:
    """Returns (food_name, risk, confidence) or None if unable / low confidence."""
    if not _ensure_model() or image is None:
        return None
    import numpy as np  # local import to keep cold start cheap

    inp = _input_details[0]  # type: ignore[index]
    h, w = inp["shape"][1], inp["shape"][2]
    img = image.resize((w, h)).convert("RGB")
    arr = np.expand_dims(np.asarray(img, dtype=np.uint8), 0)
    _interpreter.set_tensor(inp["index"], arr)  # type: ignore[union-attr]
    _interpreter.invoke()  # type: ignore[union-attr]
    out = _interpreter.get_tensor(_output_details[0]["index"])[0]  # type: ignore[index, union-attr]
    idx = int(out.argmax())
    confidence = float(out[idx]) / 255.0  # quantised model
    if confidence < TUNABLES.food_min_confidence:
        return None
    label = _labels[idx] if idx < len(_labels) else f"class_{idx}"
    entry = lookup(label) or lookup(label.replace("_", " "))
    if entry is None:
        return (label, "MEDIUM", confidence)
    return (entry.name, entry.risk, confidence)
