import copy
import json

import pytest

from pipeline import bakeoff, scene_spec
from pipeline.common import REPO_ROOT

SHOT = {
    "id": "T1", "teaches": "broadcast thinly", "framing": "medium shot, 35 mm lens", "setting": "a field at dawn",
    "crop_stage": "{stage:young_wheat}",
    "people": [{"role": "farmer", "gender": "man", "age": "about 45", "clothes": "a white kurta",
                "posture": "walking", "left_hand": {"holds": "steel bucket", "grip": "bucket handle on the forearm"},
                "right_hand": {"holds": None, "grip": "open hand, fingers spread"}}],
    "objects": [{"name": "stainless-steel bucket", "count": 1, "state": "full", "support": "on his forearm"}],
    "flows": [{"material": "granules", "source": "leaving his open right hand", "landing": "spread on the soil"}],
}


def test_complete_spec_passes_and_renders_every_hand():
    errs, _, prompt = scene_spec.check(SHOT)
    assert errs == []
    assert "His left hand: bucket handle on the forearm." in prompt
    assert "His right hand: open hand, fingers spread." in prompt
    assert "{" not in prompt  # tokens expanded


@pytest.mark.parametrize("mutate,expect", [
    (lambda s: s["people"][0].pop("right_hand"), "right_hand not accounted for"),
    (lambda s: s["people"][0]["left_hand"].update(holds="sickle"), "no object in objects[] matches"),
    (lambda s: s["objects"][0].pop("support"), "has no support"),
    (lambda s: s.update(flows=[]), "flows[] is empty"),
    (lambda s: s["flows"][0].update(source="from his fist"), "must name an open hand"),
    (lambda s: s["people"][0].update(gender="m"), "gender must be"),
])
def test_lint_catches_gaps(mutate, expect):
    s = copy.deepcopy(SHOT)
    mutate(s)
    assert any(expect in e for e in scene_spec.lint(s))


def test_rendered_prompt_goes_through_negation_lint():
    s = copy.deepcopy(SHOT)
    s["setting"] = "a field with no palm trees"
    errs, _, _ = scene_spec.check(s)
    assert errs and "doesn't want" in errs[0]


def test_bakeoff_specs_all_valid():
    data = scene_spec.load(REPO_ROOT / "bakeoff" / "shots.yaml")
    assert len(data["shots"]) >= 12
    for shot in data["shots"]:
        errs, _, prompt = scene_spec.check(shot, data.get("style", ""))
        assert errs == [], errs
        assert len(prompt.split()) < 400   # stays inside the text encoders' token limits


def test_build_cmd_passes_only_set_options():
    m = {"command": "mflux-generate-z-image", "model": "z-image", "quantize": 8, "steps": 40, "extra": ["--low-ram"]}
    cmd = bakeoff.build_cmd(m, "p", 11, 1344, 768, REPO_ROOT / "x.png")
    assert cmd[:3] == ["mflux-generate-z-image", "--model", "z-image"]
    assert "--guidance" not in cmd and "--base-model" not in cmd
    assert cmd[cmd.index("--quantize") + 1] == "8" and cmd[-1] == "--low-ram"


def test_blind_ids_are_stable_and_hide_the_model(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    for model in ("m_a", "m_b"):
        (runs / model).mkdir(parents=True)
        (runs / model / "B01-s11.png").write_bytes(b"png")
    monkeypatch.setattr(bakeoff, "BLIND", tmp_path / "blind")
    monkeypatch.setattr(bakeoff, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(bakeoff, "cfg", lambda: {"specs": str(REPO_ROOT / "bakeoff" / "shots.yaml"),
                                                 "out_dir": "runs", "models": {"m_a": {}, "m_b": {}}})
    assert bakeoff.blind() == 0            # default: only models with every shot done
    assert bakeoff.blind(["m_a", "m_b"]) == 2
    items = json.loads((tmp_path / "blind" / "items.json").read_text())["items"]
    first_ids = sorted(i["id"] for i in items)
    assert all("m_a" not in json.dumps(i) and "m_b" not in json.dumps(i) for i in items)
    bakeoff.blind(["m_a", "m_b"])
    assert sorted(i["id"] for i in json.loads((tmp_path / "blind" / "items.json").read_text())["items"]) == first_ids
    rec = bakeoff.record_rating(first_ids[0], "minor", ["hands", "bogus"], "6 fingers")
    assert rec["tags"] == ["hands"]
    with pytest.raises(ValueError):
        bakeoff.record_rating(first_ids[0], "great", [], "")
    with pytest.raises(ValueError):
        bakeoff.record_rating("0000000000", "pass", [], "")


def test_round_pauses_for_queued_priority_run(tmp_path, monkeypatch):
    import os
    import subprocess as sp
    monkeypatch.setattr(bakeoff, "WAITING", tmp_path)
    monkeypatch.setattr(bakeoff, "other_heavy_jobs", lambda: [])
    other = sp.Popen(["sleep", "5"])
    (tmp_path / f"{other.pid}.pid").touch()
    (tmp_path / "999999.pid").touch()                    # stale marker: removed
    assert bakeoff._priority_waiters() == [tmp_path / f"{other.pid}.pid"]
    assert not (tmp_path / "999999.pid").exists()
    bakeoff.wait_for_quiet(priority=True)                 # priority run: marks itself, doesn't wait for others
    assert (tmp_path / f"{os.getpid()}.pid").exists()
    other.kill(); other.wait()
