"""Spec writer (pipeline/spec_writer.py, plan P3 step 2) with a fake LLM: parsing, normalising, code checks,
repair rounds and flagging."""

import copy
import json

from pipeline import spec_writer as W
from pipeline.common import load_config

CFG = load_config()
CAST = [{"id": "ramesh", "gender": "man", "role": "farmer"}, {"id": "sunita", "gender": "woman", "role": "lab technician"}]
FRAMING = CFG["shot_specs"]["framings"]["wide"]

GOOD = {
    "teaches": "a sample taken from only one corner of the field",
    "framing": "whatever the model says",
    "setting": "a harvested field on a clear morning; {setting:north_field_bg}",
    "crop_stage": "{stage:harvested_stubble}",
    "people": [{"role": "farmer", "cast": "ramesh", "gender": "male", "clothes": "a turban and kurta", "age": "50",
                "posture": "squatting at the corner of the field", "gaze": "looking at the pit",
                "left_hand": "resting flat on the soil",
                "right_hand": {"holds": "hand weeder", "grip": "gripping the short handle"}}],
    "objects": [{"name": "{prop:khurpi}", "count": 1, "state": "blade in the soil", "support": "held by his right hand"}],
    "flows": [],
    "contacts": "his right hand grips the weeder",
    "inspector_notes": ["khurpi short handle"],
}


def ctx(sentence="पहली गलती, खेत के एक ही कोने से नमूना लेना। कटाई के बाद।", **kw):
    return W.ShotContext(key="s16-k1", sentence=sentence, framing=FRAMING, cast=CAST, **kw)


class FakeLLM:
    """Answers each job id from a queue of texts; records the prompts it got."""
    def __init__(self, answers: dict[str, list[str]]):
        self.answers = {k: list(v) for k, v in answers.items()}
        self.calls: list[list[dict]] = []

    def __call__(self, jobs, model, max_tokens=0, temperature=0.0, log=None):
        self.calls.append(jobs)
        return {j["id"]: {"text": self.answers[j["id"]].pop(0), "sec": 1.0} for j in jobs}


def test_normalize_strips_cast_clothes_and_fixes_framing_and_gender():
    spec, notes = W.normalize(GOOD, ctx())
    p = spec["people"][0]
    assert "clothes" not in p and "age" not in p and p["gender"] == "man"
    assert p["left_hand"] == {"holds": None, "grip": "resting flat on the soil"}
    assert spec["framing"] == FRAMING
    assert spec["contacts"] == ["his right hand grips the weeder"]
    assert notes and "dropped" in notes[0]


def test_good_spec_passes_checks():
    spec, _ = W.normalize(GOOD, ctx())
    errors, warnings, prompt = W.check(spec, ctx(), CFG["shot_specs"], "sharp focus")
    assert errors == []
    assert prompt.startswith("Wide shot at eye level")


def test_negation_and_unknown_cast_are_errors():
    bad = copy.deepcopy(GOOD)
    bad["setting"] = "a field with no trees; {setting:north_field_bg}"
    spec, _ = W.normalize(bad, ctx())
    errors, _, _ = W.check(spec, ctx(), CFG["shot_specs"], "")
    assert any("doesn't want" in e for e in errors)
    bad2 = copy.deepcopy(GOOD)
    bad2["people"][0]["cast"] = "mohan"
    spec, _ = W.normalize(bad2, ctx())
    errors, _, _ = W.check(spec, ctx(), CFG["shot_specs"], "")
    assert any('cast "mohan"' in e for e in errors)


def test_required_stage_token():
    bad = copy.deepcopy(GOOD)
    bad["crop_stage"] = "dry field"
    spec, _ = W.normalize(bad, ctx())
    errors, _, _ = W.check(spec, ctx(), CFG["shot_specs"], "")
    assert any("{stage:harvested_stubble}" in e for e in errors)


def test_too_many_cast_members():
    many = copy.deepcopy(GOOD)
    sun = {"role": "technician", "cast": "sunita", "gender": "woman", "posture": "standing", "gaze": "at him",
           "left_hand": {"holds": None, "grip": "at her side"}, "right_hand": {"holds": None, "grip": "at her side"}}
    many["people"] += [sun, dict(sun)]
    spec, _ = W.normalize(many, ctx())
    errors, _, _ = W.check(spec, ctx(), CFG["shot_specs"], "")
    assert any("at most 2" in e for e in errors) and any("twice" in e for e in errors)


def test_repair_round_fixes_a_bad_first_answer():
    bad = copy.deepcopy(GOOD)
    bad["setting"] = "a field without any trees; {setting:north_field_bg}"
    llm = FakeLLM({"s16-k1": ["```json\n" + json.dumps(bad, ensure_ascii=False) + "\n```", json.dumps(GOOD, ensure_ascii=False)]})
    r = W.write_specs([ctx()], CFG, llm=llm, progress=lambda m: None)["s16-k1"]
    assert r.ok and r.rounds == 1 and len(llm.calls) == 2
    repair = llm.calls[1][0]["prompt"]
    assert "Code checks rejected it" in repair and "without" in repair


def test_still_failing_after_last_round_is_flagged_not_dropped():
    bad = copy.deepcopy(GOOD)
    bad["people"][0]["right_hand"] = {"holds": "hammer", "grip": "holding a hammer"}
    n = CFG["shot_specs"]["max_repair_rounds"] + 1
    llm = FakeLLM({"s16-k1": [json.dumps(bad)] * n})
    r = W.write_specs([ctx()], CFG, llm=llm, progress=lambda m: None)["s16-k1"]
    assert not r.ok and r.spec is not None and r.rounds == n - 1
    assert any("hammer" in e for e in r.errors)
    assert len(llm.calls) == n


def test_unparseable_answer_is_an_error():
    llm = FakeLLM({"s16-k1": ["I cannot do that."] * 4})
    r = W.write_specs([ctx()], CFG, llm=llm, progress=lambda m: None)["s16-k1"]
    assert not r.ok and r.spec is None and "no JSON" in r.errors[0]


def test_examples_are_similar_and_deterministic():
    pool = W.example_pool(CFG["shot_specs"])
    assert "B01" not in [s["id"] for s in pool]
    assert all("clothes" not in p for s in pool for p in s.get("people") or [] if p.get("cast"))
    c = ctx(sentence="खुरपी से V आकार का गड्ढा खोदें।")
    ids = [s["id"] for s in W.pick_examples(pool, c, CFG["shot_specs"])]
    assert ids[0] == "B03" and len(ids) == CFG["shot_specs"]["examples"]
    assert ids == [s["id"] for s in W.pick_examples(pool, c, CFG["shot_specs"])]
    c.exclude_examples = ["B03"]
    assert "B03" not in [s["id"] for s in W.pick_examples(pool, c, CFG["shot_specs"])]


def test_prompt_has_context_and_revise_note():
    c = ctx(topic="मिट्टी की जांच", purpose="mistake", before="पहले", after="बाद")
    u = W.user_prompt(c, [])
    assert "मिट्टी की जांच" in u and "Scene purpose: mistake" in u and FRAMING in u and '"ramesh"' in u
    assert "{stage:harvested_stubble}" in u   # required token for कटाई
    c.old_spec, c.note = GOOD, "closed fist pouring"
    assert "Rewrite it to fix this: closed fist pouring" in W.user_prompt(c, [])
    assert "Library tokens" in W.system_prompt(CFG["shot_specs"])


def test_malformed_slots_become_errors_not_crashes():
    bad = copy.deepcopy(GOOD)
    bad["objects"][0]["count"] = "many"
    spec, _ = W.normalize(bad, ctx())
    errors, _, _ = W.check(spec, ctx(), CFG["shot_specs"], "")
    assert any("whole number" in e for e in errors)
    bad = copy.deepcopy(GOOD)
    bad["people"][0]["gender"] = "man"
    bad["people"][0]["left_hand"] = {"holds": None, "grip": None}
    spec, _ = W.normalize(bad, ctx())
    errors, _, _ = W.check(spec, ctx(), CFG["shot_specs"], "")
    assert errors


def test_holds_token_matches_expanded_object_and_count_text():
    s = copy.deepcopy(GOOD)
    s["people"][0]["right_hand"] = {"holds": "{prop:khurpi}", "grip": "gripping the short handle"}
    s["objects"][0]["count"] = "1 small one"
    spec, _ = W.normalize(s, ctx())
    assert spec["objects"][0]["count"] == 1
    errors, _, _ = W.check(spec, ctx(), CFG["shot_specs"], "")
    assert errors == []
