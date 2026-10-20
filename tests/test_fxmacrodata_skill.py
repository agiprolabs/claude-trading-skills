import importlib.util
import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/fxmacrodata/scripts"))

from fxmacrodata_skill import build_context
from fxmacrodata_skill._fxmacrodata_client import Result

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fxmacrodata_cli", ROOT / "skills/fxmacrodata/scripts/fxmacrodata.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def test_installed_plugin_discovers_skill_and_references():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert plugin["name"] == "trading-skills"
    skill = ROOT / "skills/fxmacrodata"
    text = (skill / "SKILL.md").read_text()
    assert "name: fxmacrodata" in text and "utm_campaign=claude-trading-skills" in text
    assert (skill / "references/usd-requests.json").is_file()
    assert len(text.splitlines()) < 500


def test_list_and_schema_need_no_network(capsys):
    assert cli.main(["list"]) == 0
    operations = json.loads(capsys.readouterr().out)
    assert len(operations) == 91
    assert cli.main(["schema", "indicator_history"]) == 0
    assert json.loads(capsys.readouterr().out)["input_schema"]["required"] == ["currency", "indicator"]


def test_default_brief_is_public_usd_and_saves_source_payload(monkeypatch, capsys, tmp_path):
    calls = []
    class Fake:
        def execute(self, operation, arguments):
            calls.append((operation, arguments))
            return Result(operation, {"data": [{"fixture": "skill-smoke"}]})
        def close(self):
            pass
    def context(requests, **kwargs):
        return build_context(requests, client=Fake(), **kwargs)
    monkeypatch.setattr(cli, "build_context", context)
    target = tmp_path / "brief.json"
    assert cli.main(["brief", "--output", str(target)]) == 0
    assert calls == [("data_catalogue", {"currency": "usd"}), ("release_calendar", {"currency": "usd"})]
    assert "skill-smoke" in capsys.readouterr().out
    assert len(json.loads(target.read_text())["results"]) == 2


def test_invalid_json_is_a_safe_nonzero_exit(capsys):
    assert cli.main(["call", "indicator_history", "--arguments", "invalid"]) == 1
    assert "Traceback" not in capsys.readouterr().err
