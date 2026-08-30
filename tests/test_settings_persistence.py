import json
import pytest
from pathlib import Path
import web_app


def test_settings_persistence(tmp_path, monkeypatch):
    test_settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(web_app, "SETTINGS_PATH", test_settings_file)

    web_app.STATE["temperature"] = 0.85
    web_app.STATE["auto_continue"] = True
    web_app.STATE["context_token_budget"] = 48000
    web_app._save_persisted_settings()

    assert test_settings_file.exists()
    content = json.loads(test_settings_file.read_text(encoding="utf-8"))
    assert content["temperature"] == 0.85
    assert content["context_token_budget"] == 48000

    # Reset STATE and test loading
    web_app.STATE["temperature"] = 0.1
    web_app.STATE["context_token_budget"] = 4000
    web_app._load_persisted_settings()

    assert web_app.STATE["temperature"] == 0.85
    assert web_app.STATE["context_token_budget"] == 48000
