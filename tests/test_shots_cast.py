"""Multi-shot image scenes and recurring cast (schema v2)."""

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from pipeline.common import shot_starts_sec
from pipeline.schema import Episode, Scene, Status

FIXTURE = Path(__file__).parent / "fixtures" / "sample-episode"


def test_v1_scene_migrates_to_one_shot():
    s = Scene.model_validate({
        "id": 1, "purpose": "hook", "narration_display": "x",
        "visual": {"type": "image", "image_prompt": "farmer", "seed": 5, "attempts": 2,
                   "inspection": {"file_sha1": "ab", "passed": True}},
        "image_file": "images/scene-01.png"})
    (sh,) = s.visual.shots
    assert (sh.image_prompt, sh.seed, sh.attempts, sh.image_file) == ("farmer", 5, 2, "images/scene-01.png")
    assert sh.inspection.passed and s.image_files() == ["images/scene-01.png"]
    # graphic scenes migrate to no shots
    g = Scene.model_validate({"id": 2, "purpose": "recap", "narration_display": "x",
                              "visual": {"type": "graphic", "template": "TitleCard", "props": {"title": "t"}}})
    assert g.visual.shots == [] and g.image_files() == []


def test_v1_episode_upgrades_version():
    data = json.loads((FIXTURE / "episode.json").read_text(encoding="utf-8"))
    data["schema_version"] = 1
    assert Episode.model_validate(data).schema_version == 2


def test_shot_order_rules():
    base = {"id": 1, "purpose": "explain", "narration_display": "x"}
    with pytest.raises(ValidationError):
        Scene.model_validate({**base, "visual": {"type": "image", "shots": [{"at_segment": 1}]}})
    with pytest.raises(ValidationError):
        Scene.model_validate({**base, "visual": {"type": "image", "shots": [{"at_segment": 0}, {"at_segment": 2},
                                                                              {"at_segment": 2}]}})


def _scene(shots, segments=None, dur=9.0):
    return Scene.model_validate({
        "id": 3, "purpose": "explain", "narration_display": "x",
        "visual": {"type": "image", "shots": [{"at_segment": j} for j in shots]},
        "audio": {"file": "a.wav", "duration_sec": dur, "segments": segments or []}})


def test_shot_starts_cut_in_the_pause():
    segs = [{"text": "a", "start": 0.1, "end": 3.0}, {"text": "b", "start": 3.6, "end": 6.0},
            {"text": "c", "start": 6.4, "end": 8.9}]
    assert shot_starts_sec(_scene([0, 2], segs), lead_in_sec=0.4) == pytest.approx([0.0, 0.4 + 6.2])
    # no segment timings (scene-mode audio): split evenly
    assert shot_starts_sec(_scene([0, 1, 2]), lead_in_sec=0.4) == pytest.approx([0.0, 3.4, 6.4])


@pytest.fixture
def cast_lib(tmp_path, monkeypatch):
    import pipeline.cast as cast
    monkeypatch.setattr(cast, "CAST_DIR", tmp_path / "cast")
    c = cast.CastMember(id="ramesh", name_hi="रमेश जी", name_en="Ramesh", role="farmer", gender="male",
                        look="a 48-year-old farmer, grey moustache", wardrobe="white kurta, green gamchha")
    cast.save_character(c)
    return cast


def test_reference_needs_user_approval(cast_lib):
    c = cast_lib.load_character("ramesh")
    assert cast_lib.reference_problems(c)  # no approved reference yet
    cand = cast_lib.char_dir("ramesh") / "candidates" / "c1.png"
    cand.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), "white").save(cand)
    cast_lib.cmd_approve(type("A", (), {"id": "ramesh", "candidate": 1})())
    c = cast_lib.load_character("ramesh")
    assert not cast_lib.reference_problems(c) and c.approved_at
    Image.new("RGB", (32, 32), "black").save(cast_lib.char_dir("ramesh") / "ref.png")
    assert "changed after approval" in cast_lib.reference_problems(c)[0]


def test_reference_preamble_names_and_wardrobe(cast_lib):
    pre = cast_lib.reference_preamble([cast_lib.load_character("ramesh")])
    assert "Ramesh is the man in reference image 1" in pre
    assert "white kurta, green gamchha" in pre and "nothing else added on the head" in pre


def test_validate_cast_shots(tmp_path, cast_lib):
    from pipeline.validate import validate
    ep = tmp_path / "ep"
    shutil.copytree(FIXTURE, ep)
    data = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    s0 = data["scenes"][0]
    s0.pop("image_file", None)
    s0["visual"] = {"type": "image", "shots": [
        {"at_segment": 0, "image_prompt": "Ramesh in his field", "seed": 1, "characters": ["ramesh"]}]}

    def errs(cast):
        data["cast"] = cast
        (ep / "episode.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        rep, _ = validate(ep, Status.visuals_ready)
        return rep.errors + rep.warnings

    found = errs([])
    assert any("not in episode.cast" in e for e in found)
    found = errs(["ramesh"])
    assert any("no approved reference" in e for e in found)
    assert not any("narration names" in e for e in found)


def test_pass_notes_need_action_check():
    from pipeline.images import pass_notes_problem
    assert pass_notes_problem("", False)
    assert "action:" in pass_notes_problem("farmer: 2 arms, 2 legs", False)
    assert pass_notes_problem("farmer: 2 arms; action: static", False) is None
    assert "identity" in pass_notes_problem("ramesh: 2 arms; action: static", True)
    assert pass_notes_problem("ramesh: 2 arms; action: granules leave open palm; identity: match", True) is None
