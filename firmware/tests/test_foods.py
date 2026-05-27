import json

from upright import config
from upright.services import foods


def test_load_real_foods_json():
    d = foods.load(config.FOODS_PATH)
    assert len(d) > 100
    assert "pizza" in d
    assert d["pizza"].risk == "HIGH"


def test_lookup_case_insensitive():
    foods.load(config.FOODS_PATH)
    assert foods.lookup("Pizza") is not None
    assert foods.lookup("PIZZA") is not None


def test_upsert_roundtrip(tmp_path):
    path = tmp_path / "foods.json"
    path.write_text(json.dumps({"apple": {"risk": "LOW", "upright_hours": 2.0}}))
    foods.load(path)
    foods.upsert("mystery dish", "MEDIUM", 2.5)
    foods.save(path)
    reloaded = json.loads(path.read_text())
    assert "mystery dish" in reloaded
