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


def test_classify_maps_food101_label():
    foods.reload(config.FOODS_PATH)
    fake_img = MagicMock()
    fake_img.resize.return_value.convert.return_value = fake_img
    fake_out = np.zeros(101, dtype=np.float32)
    fake_out[76] = 10.0  # pizza index in alphabetical Food-101
    probs = fake_out / fake_out.sum()

    mock_interp = MagicMock()
    mock_interp.get_input_details.return_value = [{"index": 0, "shape": [1, 224, 224, 3], "dtype": np.uint8}]
    mock_interp.get_output_details.return_value = [{"index": 0}]

    def get_tensor(_idx):
        return np.array([probs])

    mock_interp.get_tensor.side_effect = get_tensor

    with patch.object(foods, "_ensure_model", return_value=True):
        foods._interpreter = mock_interp
        foods._input_details = mock_interp.get_input_details()
        foods._output_details = mock_interp.get_output_details()
        foods._labels = (config.FIRMWARE_ROOT / "models" / "food_mobilenetv2_quant.labels.txt").read_text().splitlines()
        result = foods.classify(fake_img)

    assert result is not None
    assert result.name == "Pizza"
    assert result.risk == "HIGH"
    assert result.gerd_score >= 70
    foods._interpreter = None


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
