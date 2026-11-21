"""Phase 5: timing parity with Remotion, package checks, youtube.md, review helpers."""

import json
from pathlib import Path

from pipeline.common import episode_frames, load_config
from pipeline.package import is_synthetic, problems, write_youtube_md
from pipeline.review import fmt_t
from pipeline.schema import Audio, Episode

FIXTURE = Path(__file__).parent / "fixtures" / "sample-episode"


def sample() -> Episode:
    return Episode.model_validate(json.loads((FIXTURE / "episode.json").read_text(encoding="utf-8")))


def test_episode_frames_matches_remotion_formula():
    ep, cfg = sample(), load_config()
    cfg["video"].update(scene_padding_sec=0.35, scene_lead_in_sec=0.0)  # the settings of that real render
    durs = [7.343, 8.337, 7.705, 6.782]  # phase5-test narration; Remotion rendered 30.61 s
    for s, d in zip(ep.scenes, durs):
        s.audio = Audio(file="x.wav", duration_sec=d)
    assert abs(episode_frames(ep, cfg) / 30 - 30.60) < 0.04


def test_package_problems():
    ep = sample()
    errs, _ = problems(ep)
    assert any("youtube_title" in e for e in errs)
    ep.package.youtube_title = "क" * 70
    ep.package.description_hi = "x [VERIFY: date]"
    ep.package.thumbnail_text = "एक दो"
    errs, warns = problems(ep)
    assert any("< 70" in e for e in errs) and any("VERIFY" in e for e in errs)
    assert any("3–5" in w for w in warns) and any("tags" in w for w in warns)


def test_synthetic_disclosure_and_youtube_md(tmp_path: Path):
    ep = sample()
    assert is_synthetic(ep)  # fixture has an image scene
    ep.format, ep.video.width, ep.video.height = "short", 1080, 1920
    ep.package.youtube_title = "मिट्टी की जांच"
    ep.package.description_hi = "सारांश"
    ep.package.tags = ["a"] * 10
    out = write_youtube_md(ep, tmp_path, "अस्वीकरण")
    md = out.read_text(encoding="utf-8")
    assert "मिट्टी की जांच #Shorts" in md
    assert "Altered or synthetic content: YES" in md
    assert "fixture-notes.md" in md and "अस्वीकरण" in md


def test_fmt_t():
    assert fmt_t(0) == "0:00.0" and fmt_t(125.5) == "2:05.5"


def test_caption_font_size_from_config():
    from pipeline.render import caption_font_size
    cfg = load_config()
    assert caption_font_size(cfg, "long") == 56 and caption_font_size(cfg, "short") == 64
    assert caption_font_size({"captions": {"font_size_px": 70}}, "long") == 70
    assert caption_font_size({}, "long") is None


def test_style_suffix_is_positive_only():
    """klein has no negative prompt: the suffix must not name what it doesn't want (A/B 2026-11-20),
    and must not push toward blank paper or bare walls either."""
    from pipeline.visual_rules import lint
    suffix = load_config()["images"]["style_suffix"]
    errors, _ = lint(suffix)
    assert errors == [] and "no text" not in suffix
