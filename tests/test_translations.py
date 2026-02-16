"""Test to ensure that all translation keys are present."""

import json
from pathlib import Path

from custom_components.tibber_prices.const import DOMAIN


def test_string_keys_match_translations():
    """Test that keys in strings.json match keys in all translation files."""
    base_path = Path(__file__).parent.parent / "custom_components" / DOMAIN
    strings_json_path = base_path / "strings.json"
    translations_path = base_path / "translations"

    assert strings_json_path.exists(), "strings.json not found"
    assert translations_path.exists(), "translations directory not found"

    with open(strings_json_path, "r", encoding="utf-8") as f:
        strings_data = json.load(f)

    # Helper function to recursively get all keys
    def get_all_keys(data, parent_key=""):
        keys = set()
        for k, v in data.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            if isinstance(v, dict):
                keys.update(get_all_keys(v, new_key))
            else:
                keys.add(new_key)
        return keys

    strings_keys = get_all_keys(strings_data)

    # Check all json files in translations directory
    for lang_file in translations_path.glob("*.json"):
        with open(lang_file, "r", encoding="utf-8") as f:
            lang_data = json.load(f)

        lang_keys = get_all_keys(lang_data)

        # It's okay if translation has extra keys (e.g. ancient ones),
        # but it MUST have all keys from strings.json
        missing_in_lang = strings_keys - lang_keys

        assert not missing_in_lang, (
            f"Keys present in strings.json but missing in {lang_file.name}: {missing_in_lang}"
        )
