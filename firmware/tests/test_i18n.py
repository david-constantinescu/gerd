"""i18n locale loading."""

from upright.config import TUNABLES
from upright.services.i18n import reload_locales, t


def test_english_strings():
    reload_locales()
    TUNABLES.language = "en"
    assert t("menu.log_water") == "Log Water"
    assert t("flash.water_logged") == "Water logged"


def test_romanian_strings():
    reload_locales()
    TUNABLES.language = "ro"
    assert t("menu.log_water") == "Apa"
    assert t("flash.water_logged") == "Apa inregistrata"


def test_format_kwargs():
    reload_locales()
    TUNABLES.language = "en"
    assert "62" in t("flash.sleep_morning", score=62)
