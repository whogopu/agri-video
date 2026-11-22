"""Shot plan by code (pipeline/shot_specs.py, plan P3 step 1): deterministic, from narration segment timings.
Segment timings are v3's (episodes/2026-11-20-mitti-ki-jaanch-v3), copied here so the test stands alone."""

import copy

import pytest

from pipeline.common import load_config, shot_starts_sec
from pipeline.schema import Episode, Scene, Shot, Visual
from pipeline.shot_specs import FRAMING_SEQ, framings_for, plan_cuts, plan_episode, plan_scene

CFG = load_config()
LEAD = CFG["video"]["scene_lead_in_sec"]
PAD = CFG["video"]["scene_padding_sec"]
LO, HI = CFG["shots"]["min_shot_sec"], CFG["shots"]["max_shot_sec"]

# scene id → (audio duration, [(start, end) per segment]); scenes 2, 6, 10, 11, 14, 17, 21–23 are graphics
V3 = {
    1: (8.55, [(0.0, 2.54), (3.04, 8.55)]),
    3: (11.74, [(0.0, 7.18), (7.5, 11.74)]),
    4: (8.45, [(0.0, 5.14), (5.46, 8.45)]),
    5: (10.27, [(0.0, 3.38), (3.7, 10.27)]),
    7: (9.94, [(0.0, 5.69), (6.01, 9.94)]),
    8: (9.6, [(0.0, 5.09), (5.41, 9.6)]),
    9: (8.737, [(0.0, 1.62), (1.94, 8.74)]),
    12: (5.08, [(0.0, 5.08)]),
    13: (10.88, [(0.0, 4.97), (5.29, 10.88)]),
    15: (13.56, [(0.0, 6.33), (6.65, 10.55), (10.87, 13.56)]),
    16: (8.93, [(0.0, 1.37), (1.69, 4.97), (5.29, 8.93)]),
    18: (9.0, [(0.0, 4.91), (5.23, 9.0)]),
    19: (8.12, [(0.0, 4.36), (4.68, 8.12)]),
    20: (9.3, [(0.0, 5.45), (5.77, 9.3)]),
}
GRAPHICS = {2, 6, 10, 11, 14, 17, 21, 22, 23}
EXPECTED = {   # scene → [(at_segment, framing)]
    1: [(0, "wide"), (1, "medium")], 3: [(0, "wide"), (1, "medium")], 4: [(0, "wide"), (1, "medium")],
    5: [(0, "wide"), (1, "medium")], 7: [(0, "wide"), (1, "medium")], 8: [(0, "wide"), (1, "medium")],
    9: [(0, "wide"), (1, "medium")], 12: [(0, "medium_wide")], 13: [(0, "wide"), (1, "medium")],
    15: [(0, "wide"), (1, "medium"), (2, "close")], 16: [(0, "wide"), (2, "medium")],
    18: [(0, "wide"), (1, "medium")], 19: [(0, "wide"), (1, "medium")], 20: [(0, "wide"), (1, "medium")],
}


def _scene(sid: int, dur: float, segs: list[tuple[float, float]]) -> dict:
    return {"id": sid, "purpose": "step", "narration_display": "।".join("क" for _ in segs) + "।",
            "visual": {"type": "image"},
            "audio": {"file": f"audio/scene-{sid:02d}.wav", "duration_sec": dur,
                      "segments": [{"text": "क।", "start": a, "end": b} for a, b in segs]}}


def _v3() -> Episode:
    scenes = []
    for sid in range(1, 24):
        if sid in GRAPHICS:
            scenes.append({"id": sid, "purpose": "explain", "narration_display": "ग।", "visual": {"type": "graphic"}})
        else:
            scenes.append(_scene(sid, *V3[sid]))
    return Episode.model_validate({"id": "v3", "scenes": scenes})


def test_v3_plan_matches_expected():
    plans = plan_episode(_v3(), CFG)
    assert {sid: [(p.at_segment, p.framing) for p in plan] for sid, plan in plans.items()} == EXPECTED
    assert sum(len(p) for p in plans.values()) == 28


def test_plan_is_deterministic():
    a = plan_episode(_v3(), CFG)
    b = plan_episode(_v3(), CFG)
    assert a == b


def test_plan_times_match_render_timing():
    """Shot start times equal common.shot_starts_sec (mirror of remotion timing.ts) for the planned shots."""
    ep = _v3()
    for sid, plan in plan_episode(ep, CFG).items():
        s = copy.deepcopy(ep.scene(sid))
        s.visual = Visual(type="image", shots=[Shot(at_segment=p.at_segment) for p in plan])
        assert [round(x, 6) for x in shot_starts_sec(s, LEAD)] == [round(p.start, 6) for p in plan]
        assert plan[-1].end == pytest.approx(LEAD + s.audio.duration_sec + PAD)


def test_every_v3_shot_within_limits_where_possible():
    for sid, plan in plan_episode(_v3(), CFG).items():
        if sid == 9:   # 2.2 s + 7.8 s or 9.9 s in one: no plan fits; the smaller overrun wins
            assert [round(p.sec, 2) for p in plan] == [2.18, 7.76]
            continue
        assert all(LO <= p.sec <= HI for p in plan), (sid, [p.sec for p in plan])


def test_short_sentence_is_merged():
    # scene 16: "अब कुछ आम गलतियां।" (1.4 s) merges into the next sentence → shots at segments 0 and 2
    plan = plan_scene(_v3().scene(16), CFG)
    assert [p.at_segment for p in plan] == [0, 2]


def test_one_shot_per_sentence_when_all_fit():
    plan = plan_scene(_v3().scene(15), CFG)
    assert [p.at_segment for p in plan] == [0, 1, 2]


def test_never_more_than_max_shots():
    cuts = [3.0, 6.0, 9.0, 12.0, 15.0]
    assert len(plan_cuts(cuts, 18.0, LO, HI, 3)) == 3


def test_no_segments_gives_one_shot():
    s = Scene.model_validate({"id": 1, "purpose": "step", "narration_display": "क।", "visual": {"type": "image"},
                              "audio": {"file": "a.wav", "duration_sec": 6.0}})
    plan = plan_scene(s, CFG)
    assert [(p.at_segment, p.framing) for p in plan] == [(0, "medium_wide")]


def test_framing_never_repeats_across_adjacent_image_scenes():
    # scene 12 (one shot, medium_wide) is followed directly by scene 13 (opens wide): no repeat
    assert framings_for(1, "medium_wide") == ["wide"]
    assert framings_for(2, "wide") == ["medium_wide", "medium"]
    ep = _v3()
    prev = None
    for s in ep.scenes:
        if s.visual.type != "image":
            prev = None
            continue
        plan = plan_episode(ep, CFG)[s.id]
        seq = ([prev] if prev else []) + [p.framing for p in plan]
        assert all(a != b for a, b in zip(seq, seq[1:])), (s.id, seq)
        prev = plan[-1].framing


def test_framing_keys_exist_in_config():
    keys = {k for seq in FRAMING_SEQ.values() for k in seq}
    assert keys <= set(CFG["shot_specs"]["framings"])
