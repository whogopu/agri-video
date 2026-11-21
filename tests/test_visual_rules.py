"""Prompt library, lint and must-show rules (pipeline/visual_rules.py, assets/visual_rules.yaml)."""
import pytest

from pipeline.visual_rules import KINDS, expand, lint, load_rules, must_show, prompt_hints, shot_sentence

RULES_YAML = """
stages:
  harvested_stubble:
    text: a flat field of bare brown soil with short cut stubble stumps
    tested: "2026-11-20"
    must_show: ["bare soil and stubble only"]
props:
  bucket:
    text: a clean, dry, empty steel bucket
risky_words:
  - {word: wheat, why: "draws standing wheat"}
narration:
  - id: after_harvest
    when_any: ["कटाई के बाद"]
    must_show: ["no standing crop"]
    hint: "{stage:harvested_stubble}"
"""


@pytest.fixture
def rules(tmp_path):
    p = tmp_path / "visual_rules.yaml"
    p.write_text(RULES_YAML, encoding="utf-8")
    return load_rules(p)


def test_expand_tokens(rules):
    out = expand("Ramesh walks across {stage:harvested_stubble}, carrying {prop:bucket}", rules)
    assert out == ("Ramesh walks across a flat field of bare brown soil with short cut stubble stumps, "
                   "carrying a clean, dry, empty steel bucket")


@pytest.mark.parametrize("prompt", [
    "a village with no palm trees",
    "Ramesh, no wristwatch",
    "a field without standing crop",
    "nothing on his head",
    "flasks that aren't steaming",
    "neem trees instead of palms",
])
def test_lint_rejects_negations(rules, prompt):
    errors, _ = lint(prompt, rules)
    assert errors and "negative prompt" in errors[0]


def test_lint_accepts_positive_and_warns_on_risky_words(rules):
    errors, warnings = lint("young green wheat, ankle-high, bare wrists, notice board on the wall", rules)
    assert errors == []                      # "notice" and "knot"-like words are not negations
    assert any("wheat" in w for w in warnings)


def test_lint_unknown_token(rules):
    errors, _ = lint("{stage:flowering_mustard} field", rules)
    assert "unknown token" in errors[0] and "harvested_stubble" in errors[0]
    errors, _ = lint("{colour:red} field", rules)
    assert "unknown token kind" in errors[0]


def test_must_show_from_tokens_and_narration(rules):
    items = must_show("Ramesh on {stage:harvested_stubble}", "नमूना कटाई के बाद लें।", rules)
    assert items == ["[stage:harvested_stubble] bare soil and stubble only",
                     "[after_harvest ← 'कटाई के बाद'] no standing crop"]
    assert prompt_hints("नमूना कटाई के बाद लें।", "", rules) == ["after_harvest: {stage:harvested_stubble}"]
    assert must_show("a lab bench", "रिपोर्ट देखें।", rules) == []


def test_shot_sentence_splits_by_segment():
    scene = {"narration_display": "पहला वाक्य। {slow}दूसरा | वाक्य। तीसरा वाक्य।"}
    shots = [{"at_segment": 0}, {"at_segment": 1}]
    assert shot_sentence(scene, shots[0], shots) == "पहला वाक्य।"
    assert shot_sentence(scene, shots[1], shots) == "दूसरा  वाक्य। तीसरा वाक्य।"


def test_repo_library_is_clean():
    """Every phrase in the real library passes its own lint and has a known kind."""
    rules = load_rules()
    for kind in KINDS:
        for key, e in rules.phrases[kind].items():
            errors, _ = lint(f"{{{kind}:{key}}}", rules)
            assert errors == [], f"{kind}:{key}: {errors}"
    for r in rules.narration:
        assert r.get("id") and r.get("when_any") and r.get("must_show")
