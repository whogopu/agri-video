"""Phase 1 acceptance: new_episode creates a folder; validate runs on a hand-written sample."""

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from pipeline.new_episode import create_episode
from pipeline.schema import Episode, Status
from pipeline.validate import count_words, validate

FIXTURE = Path(__file__).parent / "fixtures" / "sample-episode"


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    dst = tmp_path / "sample"
    shutil.copytree(FIXTURE, dst)
    return dst


def edit(ep_dir: Path, fn) -> None:
    p = ep_dir / "episode.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    fn(data)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_new_episode_creates_folder(tmp_path: Path):
    ep_dir = create_episode("mitti-ki-jaanch", date(2026, 11, 20), topic="soil test", root=tmp_path)
    assert ep_dir.name == "2026-11-20-mitti-ki-jaanch"
    for d in ["sources", "audio", "images", "render", "review"]:
        assert (ep_dir / d).is_dir()
    assert "soil test" in (ep_dir / "brief.md").read_text(encoding="utf-8")
    ep = Episode.model_validate_json((ep_dir / "episode.json").read_text(encoding="utf-8"))
    assert ep.status == Status.draft and ep.video.width == 1920
    assert "new_episode" in (ep_dir / "log.md").read_text(encoding="utf-8")

    # idempotent: a second run keeps a user-edited brief
    (ep_dir / "brief.md").write_text("edited", encoding="utf-8")
    create_episode("mitti-ki-jaanch", date(2026, 11, 20), root=tmp_path)
    assert (ep_dir / "brief.md").read_text(encoding="utf-8") == "edited"


def test_new_episode_rejects_bad_slug(tmp_path: Path):
    with pytest.raises(SystemExit):
        create_episode("Mitti Ki Jaanch", date(2026, 11, 20), root=tmp_path)


def test_sample_passes_as_draft(sample: Path):
    rep, ep = validate(sample)
    assert rep.ok, rep.render()
    assert ep is not None and len(ep.scenes) == 4
    # the fixture is short on purpose, so the length warning fires
    assert any("word count" in w for w in rep.warnings)


def test_verify_marker_blocks(sample: Path):
    edit(sample, lambda d: d["scenes"][1].update(
        narration_display="यूरिया [VERIFY: dose per acre] डालें।"))
    rep, _ = validate(sample)
    assert not rep.ok
    assert any("[VERIFY]" in e for e in rep.errors)


def test_verify_in_script_md_blocks(sample: Path):
    (sample / "script.md").write_text("| 2 | [VERIFY: date] |\n", encoding="utf-8")
    rep, _ = validate(sample)
    assert any("script.md:1" in e for e in rep.errors)


def test_factual_scene_needs_source(sample: Path):
    edit(sample, lambda d: d["scenes"][2].update(sources=[]))
    rep, _ = validate(sample)
    assert any("scene 3: no sources" in e for e in rep.errors)


def test_number_in_hook_needs_source(sample: Path):
    edit(sample, lambda d: d["scenes"][0].update(narration_display="हर साल 30% खाद बेकार जाती है।"))
    rep, _ = validate(sample)
    assert any("scene 1: no sources listed (contains a number)" in e for e in rep.errors)


def test_missing_source_file(sample: Path):
    edit(sample, lambda d: d["scenes"][1].update(sources=["sources/nope.pdf#p3"]))
    rep, _ = validate(sample)
    assert any("source file not found" in e for e in rep.errors)


def test_schema_error_reported(sample: Path):
    edit(sample, lambda d: d["scenes"][0].update(purpose="intro", typo_field=1))
    rep, ep = validate(sample)
    assert ep is None and any("schema:" in e for e in rep.errors)


def test_script_approved_requires_spoken_text(sample: Path):
    rep, _ = validate(sample, Status.script_approved)
    assert any("narration_spoken is empty" in e for e in rep.errors)


def test_count_words_ignores_danda():
    assert count_words("मिट्टी की जांच । कृषि ज़्यादा") == 5


def test_new_episode_short_format(tmp_path: Path):
    ep_dir = create_episode("urea-tip", date(2026, 11, 20), root=tmp_path, fmt="short")
    ep = Episode.model_validate_json((ep_dir / "episode.json").read_text(encoding="utf-8"))
    assert ep.format == "short" and (ep.video.width, ep.video.height) == (1080, 1920)
    assert "YouTube Short" in (ep_dir / "brief.md").read_text(encoding="utf-8")


def test_short_uses_short_word_target(sample: Path):
    def to_short(d):
        d["format"] = "short"
        d["video"].update(width=1080, height=1920)
    edit(sample, to_short)
    rep, ep = validate(sample)
    assert rep.ok, rep.render()
    # 79 words is inside the short target (70–140), so no length warning
    assert not any("word count" in w for w in rep.warnings)


def test_format_must_match_orientation(sample: Path):
    edit(sample, lambda d: d.update(format="short"))  # still 1920x1080
    rep, ep = validate(sample)
    assert ep is None and any("does not match video size" in e for e in rep.errors)


def test_voice_presets(tmp_path: Path):
    default = create_episode("a", date(2026, 11, 20), root=tmp_path)
    aman = create_episode("b", date(2026, 11, 20), root=tmp_path, voice="aman")
    load = lambda d: Episode.model_validate_json((d / "episode.json").read_text(encoding="utf-8"))  # noqa: E731
    female = create_episode("d", date(2026, 11, 20), root=tmp_path, voice="veena_varun")
    assert (load(default).voice.preset, load(default).voice.speaker) == ("maya_vasant", "Vasant")
    assert load(default).voice.backend == "mlx_audio"  # the preset's backend, not the global tts.backend
    assert (load(female).voice.preset, load(female).voice.speaker, load(female).voice.backend) == ("veena_varun", "varun", "mlx_audio")
    assert (load(aman).voice.preset, load(aman).voice.speaker, load(aman).voice.backend) == ("aman", "Aman", "parler")
    assert load(aman).voice.wpm and load(aman).voice.wpm > load(default).voice.wpm
    with pytest.raises(SystemExit):
        create_episode("c", date(2026, 11, 20), root=tmp_path, voice="nobody")


def test_length_estimate_uses_voice_pace(sample: Path):
    edit(sample, lambda d: d["voice"].update(wpm=180))
    rep, _ = validate(sample)
    assert any("at 180 wpm" in i for i in rep.info)
    # long target 180–300 s at 180 wpm → 540–900 words
    assert any("540–900" in w for w in rep.warnings)
