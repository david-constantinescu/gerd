import json
from unittest.mock import MagicMock, patch

import numpy as np

from upright import config
from upright.services import foods


def test_load_real_foods_json():
    foods.reload(config.FOODS_PATH)
    d = foods.all_foods()
    assert len(d) >= 350
    pizza = foods.lookup("Pizza")
    assert pizza is not None
    assert pizza.risk == "HIGH"
    assert pizza.gerd_score >= 70


def test_lookup_case_insensitive():
    foods.reload(config.FOODS_PATH)
    assert foods.lookup("Pizza") is not None
    assert foods.lookup("pizza") is not None
    assert foods.lookup("PIZZA") is not None


def test_food101_label_alias():
    foods.reload(config.FOODS_PATH)
    entry = foods.lookup("spaghetti_bolognese")
    assert entry is not None
    assert entry.risk == "HIGH"


def test_advice_includes_hours_for_high_risk():
    foods.reload(config.FOODS_PATH)
    entry = foods.lookup("Pizza")
    assert entry is not None
    text = foods.advice_for(entry)
    assert "upright" in text.lower() or "h" in text


def test_upsert_roundtrip(tmp_path):
    path = tmp_path / "foods.json"
    path.write_text(json.dumps({"Apple": {"risk": "LOW", "upright_hours": 2.0, "gerd_score": 10}}))
    foods.reload(path)
    foods.upsert("mystery dish", "MEDIUM", 2.5, gerd_score=55)
    foods.save(path)
    reloaded = json.loads(path.read_text())
    assert "mystery dish" in reloaded
    assert reloaded["mystery dish"]["gerd_score"] == 55


def _labels() -> list[str]:
    return (
        config.FIRMWARE_ROOT / "models" / "food_mobilenetv2_quant.labels.txt"
    ).read_text().splitlines()


def _idx(label: str) -> int:
    return _labels().index(label)


def test_classify_maps_model_label():
    """A confident prediction maps to the detected dish name + a risk tier."""
    foods.reload(config.FOODS_PATH)
    labels = _labels()
    idx = labels.index("Hamburger")  # real class in the bundled AIY Food model
    fake_img = MagicMock()
    fake_img.resize.return_value.convert.return_value = fake_img
    fake_out = np.zeros(len(labels), dtype=np.float32)
    fake_out[idx] = 10.0
    probs = fake_out / fake_out.sum()

    mock_interp = MagicMock()
    mock_interp.get_input_details.return_value = [{"index": 0, "shape": [1, 192, 192, 3], "dtype": np.uint8}]
    mock_interp.get_output_details.return_value = [{"index": 0}]
    mock_interp.get_tensor.side_effect = lambda _idx: np.array([probs])

    with patch.object(foods, "_ensure_model", return_value=True):
        foods._interpreter = mock_interp
        foods._input_details = mock_interp.get_input_details()
        foods._output_details = mock_interp.get_output_details()
        foods._labels = labels
        result = foods.classify(fake_img)

    assert result is not None
    assert result.name == "Hamburger"
    assert result.risk in foods.VALID_RISKS
    foods._interpreter = None


def test_classify_rejects_background_class():
    """The model's "not food" class must never produce a result."""
    foods.reload(config.FOODS_PATH)
    labels = _labels()
    fake_out = np.zeros(len(labels), dtype=np.float32)
    fake_out[0] = 10.0  # index 0 == __background__
    probs = fake_out / fake_out.sum()
    mock_interp = MagicMock()
    mock_interp.get_input_details.return_value = [{"index": 0, "shape": [1, 192, 192, 3], "dtype": np.uint8}]
    mock_interp.get_output_details.return_value = [{"index": 0}]
    mock_interp.get_tensor.side_effect = lambda _idx: np.array([probs])
    fake_img = MagicMock()
    fake_img.resize.return_value.convert.return_value = fake_img
    with patch.object(foods, "_ensure_model", return_value=True):
        foods._interpreter = mock_interp
        foods._input_details = mock_interp.get_input_details()
        foods._output_details = mock_interp.get_output_details()
        foods._labels = labels
        result = foods.classify(fake_img)
    foods._interpreter = None
    assert result is None


def test_keyword_risk_fallback():
    """Any recognized dish maps to a sensible GERD risk, even if not in foods.json."""
    foods.reload(config.FOODS_PATH)
    assert foods._risk_from_keywords("Deep-fried onion rings") == "HIGH"
    assert foods._risk_from_keywords("Steamed broccoli") == "LOW"
    # An unknown-to-the-dictionary fried dish still resolves, keeping its name.
    entry = foods.resolve_label("Crispy fried widget")
    assert entry is not None
    assert entry.name == "Crispy fried widget"
    assert entry.risk == "HIGH"
    assert foods.resolve_label("__background__") is None


def test_classify_uses_zero_shot_image_and_candidate_labels():
    foods.reload(config.FOODS_PATH)
    fake_img = MagicMock()
    fake_img.resize.return_value.convert.return_value = fake_img
    fake_pipeline = MagicMock(
        return_value=[
            {"label": "pizza", "score": 0.92},
            {"label": "salad", "score": 0.07},
        ]
    )

    with patch.object(foods, "_zero_shot_pipeline", fake_pipeline), patch.object(
        foods, "_ensure_model", return_value=False
    ):
        result = foods.classify(fake_img)

    assert result is not None
    assert result.name == "Pizza"
    assert result.confidence == 0.92
    _, kwargs = fake_pipeline.call_args
    assert kwargs["images"] is fake_img
    assert "pizza" in kwargs["candidate_labels"]
    assert len(kwargs["candidate_labels"]) > 100


def _mock_quantized_interp(raw_uint8, scale, zero_point):
    """A mock interpreter whose output tensor is raw uint8 with quant params."""
    mock_interp = MagicMock()
    mock_interp.get_input_details.return_value = [
        {"index": 0, "shape": [1, 192, 192, 3], "dtype": np.uint8}
    ]
    mock_interp.get_output_details.return_value = [
        {"index": 0, "dtype": np.uint8, "quantization": (scale, zero_point)}
    ]
    mock_interp.get_tensor.side_effect = lambda _idx: np.array([raw_uint8])
    return mock_interp


def _run_classify_tflite(mock_interp):
    fake_img = MagicMock()
    fake_img.resize.return_value.convert.return_value = fake_img
    labels = (
        config.FIRMWARE_ROOT / "models" / "food_mobilenetv2_quant.labels.txt"
    ).read_text().splitlines()
    with patch.object(foods, "_ensure_model", return_value=True):
        foods._interpreter = mock_interp
        foods._input_details = mock_interp.get_input_details()
        foods._output_details = mock_interp.get_output_details()
        foods._labels = labels
        result = foods.classify(fake_img)
    foods._interpreter = None
    return result


def test_classify_dequantizes_uint8_output():
    """Quantized uint8 output must be dequantized into a real probability.

    Regression: previously raw uint8 scores were softmaxed, collapsing the top
    class to ~1.0 confidence regardless of the model's true certainty.
    """
    foods.reload(config.FOODS_PATH)
    idx = _idx("Hamburger")
    raw = np.zeros(len(_labels()), dtype=np.uint8)
    raw[idx] = 200  # → 200/255 ≈ 0.78
    raw[1] = 55     # filler mass so the distribution sums to 255 (≈1.0)
    result = _run_classify_tflite(_mock_quantized_interp(raw, 1 / 255.0, 0))
    assert result is not None
    assert result.name == "Hamburger"
    assert 0.70 <= result.confidence <= 0.85  # genuine prob, not bogus ~1.0


def test_classify_rejects_low_confidence_quantized():
    """A weak quantized prediction must fall below food_min_confidence → None."""
    foods.reload(config.FOODS_PATH)
    raw = np.zeros(len(_labels()), dtype=np.uint8)
    # Spread mass so the top class sits at 45/255 ≈ 0.18, below the 0.20 floor.
    for i in (_idx("Hamburger"), _idx("Sushi"), _idx("Ramen"), _idx("Udon")):
        raw[i] = 45
    raw[1] = 38
    raw[2] = 37  # filler; total = 255, no class clears 0.20
    result = _run_classify_tflite(_mock_quantized_interp(raw, 1 / 255.0, 0))
    assert result is None
