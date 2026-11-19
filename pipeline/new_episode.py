"""Create a new episode folder from the template.

    uv run python -m pipeline.new_episode <slug> [--format long|short] [--date YYYY-MM-DD] [--topic "..."] [--title-hi "..."]

Idempotent: existing files are left alone (use --force to rewrite template files).
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from pipeline.common import EPISODES_DIR, REPO_ROOT, format_config, load_config, voice_preset, save_episode, setup_logging, stage_timer
from pipeline.schema import Episode, VideoSpec, VoiceSpec

TEMPLATE_DIR = REPO_ROOT / "templates" / "episode"
SUBDIRS = ["sources", "audio", "images", "render", "review"]
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def create_episode(slug: str, on: date, topic: str = "", title_hi: str = "",
                   force: bool = False, root: Path = EPISODES_DIR, fmt: str = "long",
                   voice: str | None = None) -> Path:
    if not SLUG_RE.match(slug):
        raise SystemExit(f"slug must be lowercase latin words joined by '-', e.g. mitti-ki-jaanch (got {slug!r})")
    episode_id = f"{on.isoformat()}-{slug}"
    ep_dir = root / episode_id
    ep_dir.mkdir(parents=True, exist_ok=True)
    for d in SUBDIRS:
        (ep_dir / d).mkdir(exist_ok=True)

    created: list[str] = []

    brief = ep_dir / "brief.md"
    if force or not brief.exists():
        tmpl = (TEMPLATE_DIR / "brief.md").read_text(encoding="utf-8")
        length = "30–60 s (YouTube Short, vertical)" if fmt == "short" else "3–5 min (landscape)"
        brief.write_text(tmpl.format(episode_id=episode_id, topic=topic or "<!-- topic -->",
                                     format=fmt, length=length), encoding="utf-8")
        created.append("brief.md")

    ep_json = ep_dir / "episode.json"
    if force or not ep_json.exists():
        cfg = load_config()
        f, t, vp = format_config(cfg, fmt), cfg["tts"], voice_preset(cfg, voice)
        episode = Episode(
            id=episode_id,
            title_hi=title_hi,
            format=fmt,
            video=VideoSpec(width=f["width"], height=f["height"], fps=cfg["video"]["fps"]),
            voice=VoiceSpec(preset=vp["preset"], backend=vp.get("backend", t["backend"]), speaker=vp["speaker"],
                            description=vp.get("description", ""), seed=t.get("seed"), wpm=vp.get("wpm")),
        )
        save_episode(ep_dir, episode)
        created.append("episode.json")

    log_md = ep_dir / "log.md"
    if not log_md.exists():
        log_md.write_text(f"# Log — {episode_id}\n", encoding="utf-8")
        created.append("log.md")

    with stage_timer(ep_dir, "new_episode") as run:
        run.note(f"created: {', '.join(created) or 'nothing (already existed)'}")
    return ep_dir


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("slug", help="short latin slug, e.g. mitti-ki-jaanch")
    p.add_argument("--date", type=date.fromisoformat, default=date.today(), help="episode date (default today)")
    p.add_argument("--format", choices=["long", "short"], default="long",
                   help="long = 16:9 landscape 3–5 min (default); short = 9:16 vertical Short, 30–60 s")
    p.add_argument("--voice", help="voice preset from config.yaml tts.voices (default: tts.default_voice)")
    p.add_argument("--topic", default="")
    p.add_argument("--title-hi", default="")
    p.add_argument("--force", action="store_true", help="rewrite brief.md and episode.json from template")
    args = p.parse_args()
    setup_logging()
    ep_dir = create_episode(args.slug, args.date, args.topic, args.title_hi, args.force, fmt=args.format, voice=args.voice)
    rel = ep_dir.relative_to(REPO_ROOT)
    print(f"Episode ready ({args.format}, voice {args.voice or load_config()['tts']['default_voice']}): {rel}\nNext: fill {rel}/brief.md and put source files in {rel}/sources/")


if __name__ == "__main__":
    main()
