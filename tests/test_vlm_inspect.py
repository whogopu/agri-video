"""pipeline/vlm_inspect.py: answer parsing and judging (no model needed)."""

from pipeline import vlm_inspect as v


def test_parse_json_variants():
    assert v.parse_json('```json\n{"verdict": "pass", "defects": []}\n```') == {"verdict": "pass", "defects": []}
    assert v.parse_json('<think>hmm {not json}</think> Answer: {"a": {"b": "x}y"}} trailing') == {"a": {"b": "x}y"}}
    assert v.parse_json("no json here") is None
    assert v.parse_json('{"a": 1') is None


def test_judge_full_crop_identity():
    ok = {k: {"ok": True, "issue": ""} for k in v.FULL_KEYS} | {"verdict": "pass"}
    assert v.judge("full", ok) == (False, [])
    bad = ok | {"action_physics": {"ok": False, "issue": "grain falls from closed fist"}}
    failed, why = v.judge("full", bad)
    assert failed and "closed fist" in why[0]
    assert v.judge("full", ok | {"verdict": "fail", "main_problem": "two buckets"}) == (True, ["full: two buckets"])
    assert v.judge("crop-tl", {"defects": [], "verdict": "pass"}) == (False, [])
    assert v.judge("crop-tl", {"defects": [{"what": "six fingers", "where": "left hand"}], "verdict": "fail"})[0]
    assert v.judge("identity-ramesh", {"same_person": False, "differences": ["no beard"]})[0]
    assert v.judge("identity-ramesh", {"same_person": True, "differences": [], "verdict": "pass"}) == (False, [])
    assert v.judge("crop-br", None) == (True, ["crop-br: unreadable answer"])   # unsure counts as fail


def test_illegible_text_is_not_a_defect():
    ok = {k: {"ok": True, "issue": ""} for k in v.FULL_KEYS} | {"verdict": "pass"}
    gib = ok | {"readable_text": {"ok": False, "issue": "The text on the notice board is gibberish and not readable."},
                "verdict": "fail", "main_problem": "gibberish text on notice board"}
    assert v.judge("full", gib) == (False, [])
    real = ok | {"readable_text": {"ok": False, "issue": "The sack clearly reads 'UREA 45 kg'"}}
    assert v.judge("full", real)[0]
    crop = {"defects": [{"what": "illegible scribbled writing on the board", "where": "top"}], "verdict": "fail"}
    assert v.judge("crop-tl", crop) == (False, [])
    mixed = {"defects": [{"what": "illegible letters on sack", "where": "left"},
                         {"what": "six fingers", "where": "right hand"}], "verdict": "fail"}
    assert v.judge("crop-tl", mixed) == (True, ["crop-tl: six fingers (right hand)"])
    assert not v.illegible_text_only("fused fingers, blurry hand")


def test_severity_only_major_fails():
    minor = {"issues": [{"what": "slightly odd knuckles on left hand", "severity": "minor"}], "verdict": "pass"}
    failed, why = v.judge("full", minor)
    assert not failed and why == ["full: minor: slightly odd knuckles on left hand"]   # listed, not failing
    major = {"issues": [{"what": "grain falls from a closed fist", "severity": "major"},
                        {"what": "background tree blurry", "severity": "minor"}], "verdict": "fail"}
    assert v.judge("full", major)[0]
    assert v.judge("full", {"issues": [], "verdict": "pass"}) == (False, [])
    gib = {"issues": [{"what": "gibberish text on notice board", "severity": "major"}], "verdict": "fail"}
    assert v.judge("full", gib) == (False, [])
    idm = {"same_person": True, "differences": [{"what": "face slightly fuller", "severity": "minor"}]}
    assert not v.judge("identity-ramesh", idm)[0]
    assert v.judge("identity-ramesh", {"same_person": False, "differences": [
        {"what": "lighting", "severity": "minor"}]})[0]
    assert v.judge("identity-ramesh", {"same_person": True, "differences": [
        {"what": "wears a turban the reference doesn't have", "severity": "major"}]})[0]
    shots = v.aggregate({"a.png|full": {"text": '{"issues": [{"what": "stiff pose", "severity": "minor"}]}'}})
    assert shots["a.png"]["failed"] is False and shots["a.png"]["any"] is True


def test_shot_sentence_follows_segments():
    scene = {"narration_display": "पहला वाक्य। दूसरा {slow}वाक्य। | तीसरा वाक्य।"}
    shots = [{"at_segment": 0}, {"at_segment": 2}]
    assert v.shot_sentence(scene, shots[0], shots) == "पहला वाक्य। दूसरा वाक्य।"
    assert v.shot_sentence(scene, shots[1], shots) == "तीसरा वाक्य।"


def test_fail_kinds():
    assert "hands/limbs" in v.fail_kinds("each person shows only one hand")
    assert "action/physics" in v.fail_kinds("bucket pours a liquid-like stream")


def test_compare_labels_and_reasons():
    from pathlib import Path
    from pipeline import vlm_compare as c
    assert c.model_label(Path("Qwen3.5-9B-4bit-sev2")) == "Qwen3.5-9B-4bit · major/minor"
    assert c.model_label(Path("Qwen3.5-9B-4bit")) == "Qwen3.5-9B-4bit · v1 strict"
    assert 'class="major"' in c.reason_html("full: MAJOR: grain from a closed fist")
    assert 'class="minor"' in c.reason_html("identity-ramesh: minor: face slightly fuller")
    assert 'class="v1"' in c.reason_html("crop-tl: six fingers (left hand)")


def test_sample_shots_is_balanced_and_repeatable():
    from pipeline.vlm_inspect import sample_shots
    data = [{"key": f"f{i}", "label": "fail"} for i in range(20)] + [{"key": f"p{i}", "label": "pass"} for i in range(57)]
    a, b = sample_shots(data, 20, 0), sample_shots(data, 20, 0)
    assert [d["key"] for d in a] == [d["key"] for d in b]
    assert sum(d["label"] == "fail" for d in a) == 10 and len(a) == 20
    few = sample_shots(data[:3] + data[20:], 20, 0)   # only 3 fails: top up with passes
    assert sum(d["label"] == "fail" for d in few) == 3 and len(few) == 20


def test_blank_severity_follows_verdict():
    from pipeline.vlm_inspect import judge
    item = {"what": "The wall chart is blurred and illegible-looking, so this is not an issue.", "severity": ""}
    other = {"what": "the flask meniscus is uneven", "severity": ""}
    assert judge("full", {"issues": [item, other], "verdict": "pass"})[0] is False
    assert judge("full", {"issues": [other], "verdict": "fail"})[0] is True


def test_not_legible_text_is_dropped():
    from pipeline.vlm_inspect import illegible_text_only
    assert illegible_text_only("The background charts have some text, but it is not legible enough to be considered readable")
