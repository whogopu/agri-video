"""Scene specs in production: a shot's prompt rendered from `spec` (pipeline/scene_spec.py) instead of free text."""

import argparse
import copy
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline import images, scene_spec
from pipeline.schema import Episode, Shot, Status

FIXTURE = Path(__file__).parent / "fixtures" / "sample-episode"
ICFG = {"style_suffix": "photorealistic documentary photograph, sharp focus"}

SPEC = {
    "teaches": "urea is broadcast thinly from an open hand", "framing": "medium-wide shot at eye level",
    "setting": "a North Indian field on a winter morning", "crop_stage": "{stage:young_wheat}",
    "people": [{"role": "farmer", "gender": "man", "age": "about 45", "build": "lean", "clothes": "a white kurta",
                "posture": "walking along a crop row",
                "left_hand": {"holds": "steel bucket", "grip": "carries the bucket by its wire handle"},
                "right_hand": {"holds": None, "grip": "open, fingers spread, turned downward"}}],
    "objects": [{"name": "stainless-steel bucket", "state": "upright, full of granules", "support": "in his left hand"}],
    "flows": [{"material": "white urea granules", "source": "leaving his open right hand",
               "landing": "scattered thinly over the soil"}],
    "inspector_notes": ["granules start at the open right hand"],
}


def _episode(tmp_path, shot: dict, cast=None) -> Path:
    ep = tmp_path / "ep"
    shutil.copytree(FIXTURE, ep)
    data = json.loads((ep / "episode.json").read_text(encoding="utf-8"))
    s0 = data["scenes"][0]
    s0.pop("image_file", None)
    s0["visual"] = {"type": "image", "shots": [{"at_segment": 0, **shot}]}
    data["cast"] = cast or []
    (ep / "episode.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return ep


def test_shot_takes_spec_or_prompt_not_both():
    assert Shot(spec=SPEC).spec["teaches"]
    with pytest.raises(ValidationError):
        Shot(image_prompt="a farmer", spec=SPEC)


def test_spec_shot_prompt_renders_hands_and_style():
    ep = Episode.model_validate({"id": "x", "scenes": []})
    prompt, refs, sha = images.shot_prompt(ep, Shot(spec=SPEC), ICFG, "scene 1 shot 1")
    assert "His right hand: open, fingers spread, turned downward." in prompt
    assert prompt.endswith("Photorealistic documentary photograph, sharp focus.")
    assert "{" not in prompt and "granules start" not in prompt   # tokens expanded, inspector notes never sent
    assert refs == [] and sha == {}


def test_incomplete_spec_stops_before_generating():
    s = copy.deepcopy(SPEC)
    s["people"][0].pop("right_hand")
    ep = Episode.model_validate({"id": "x", "scenes": []})
    with pytest.raises(SystemExit, match="right_hand not accounted for"):
        images.shot_prompt(ep, Shot(spec=s), ICFG, "scene 1 shot 1")


def test_cast_spec_uses_wardrobe_and_fills_characters(tmp_path, monkeypatch):
    import pipeline.cast as cast
    monkeypatch.setattr(cast, "CAST_DIR", tmp_path / "cast")
    cast.save_character(cast.CastMember(id="ramesh", name_hi="रमेश जी", name_en="Ramesh", role="farmer",
                                        gender="male", look="a farmer, grey moustache",
                                        wardrobe="white kurta, green gamchha"))
    monkeypatch.setattr(images, "cast_references",
                        lambda ep, sh: ([Path("ref.png")], "Ramesh is the man in reference image 1.", {"ramesh": "s"}))
    s = copy.deepcopy(SPEC)
    person = s["people"][0]
    person["cast"] = "ramesh"
    for k in ("clothes", "age", "build"):
        person.pop(k)
    assert scene_spec.lint(s) == []      # cast people need no clothes/age/build
    ep = Episode.model_validate({"id": "x", "cast": ["ramesh"], "scenes": []})
    sh = Shot(spec=s)
    prompt, refs, _ = images.shot_prompt(ep, sh, ICFG, "scene 1 shot 1")
    assert sh.characters == ["ramesh"] and refs == [Path("ref.png")]
    assert prompt.startswith("Ramesh is the man in reference image 1.")
    assert "He wears white kurta, green gamchha." in prompt and "about 45" not in prompt
    with pytest.raises(SystemExit, match="differ from shot.characters"):
        images.shot_prompt(ep, Shot(spec=s, characters=["sunita"]), ICFG, "scene 1 shot 1")


def _args(ep, **kw):
    base = dict(episode=str(ep), scenes=None, shots=None, force=False, retry=False, prompt=None, spec=None,
                seed=None, extra_attempt=False, dry_run=False)
    return argparse.Namespace(**{**base, **kw})


class FakeBackend:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt, seed, width, height, out_path, references=()):
        self.prompts.append(prompt)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"png")
        return 0.1


def test_stage_generates_from_spec_and_records_prompt(tmp_path, monkeypatch):
    ep_dir = _episode(tmp_path, {"spec": SPEC})
    fake = FakeBackend()
    monkeypatch.setattr(images, "get_backend", lambda icfg: fake)
    images.run_episode(_args(ep_dir, dry_run=True))
    assert fake.prompts == []                                # dry run generates nothing
    images.run_episode(_args(ep_dir))
    (prompt,) = fake.prompts
    sh = Episode.model_validate_json((ep_dir / "episode.json").read_text(encoding="utf-8")).scenes[0].visual.shots[0]
    assert sh.prompt_sent == prompt and "His left hand" in prompt
    assert (ep_dir / "images" / "scene-01-s1-a1.txt").read_text(encoding="utf-8").strip() == prompt


def test_spec_file_replaces_prompt(tmp_path, monkeypatch):
    import yaml
    ep_dir = _episode(tmp_path, {"image_prompt": "a farmer in a field"})
    f = tmp_path / "spec.yaml"
    f.write_text(yaml.safe_dump({"shots": [SPEC]}, allow_unicode=True), encoding="utf-8")
    fake = FakeBackend()
    monkeypatch.setattr(images, "get_backend", lambda icfg: fake)
    images.run_episode(_args(ep_dir, scenes=[1], shots=[1], spec=str(f)))
    sh = Episode.model_validate_json((ep_dir / "episode.json").read_text(encoding="utf-8")).scenes[0].visual.shots[0]
    assert sh.image_prompt is None and sh.spec["teaches"] == SPEC["teaches"]


def test_validate_reports_incomplete_spec(tmp_path):
    from pipeline.validate import validate
    s = copy.deepcopy(SPEC)
    s.pop("framing")
    ep_dir = _episode(tmp_path, {"spec": s, "seed": 1})
    rep, _ = validate(ep_dir, Status.visuals_ready)
    assert any("missing framing" in e for e in rep.errors)
    assert not any("no image_prompt" in e for e in rep.errors)
