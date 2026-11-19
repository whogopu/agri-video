"""Package stage: thumbnail + youtube.md from the `package` section of episode.json.

    uv run python -m pipeline.package episodes/<id> [--force]

Claude first writes episode.json `package` (youtube_title, description_hi, tags,
thumbnail_text, optional thumbnail_image / sources_list / synthetic_content). This stage
checks it, renders render/thumbnail.png with the Remotion `Thumbnail` still, and writes
youtube.md (title, description + sources + disclaimer, tags, synthetic-content disclosure).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline.common import (
    REPO_ROOT, load_config, load_episode, resolve_episode_dir, setup_logging, stage_parser,
    stage_timer, write_json,
)
from pipeline.render import BRAND_LOGO, PUBLIC, REMOTION, link_or_copy
from pipeline.schema import Episode
from pipeline.validate import count_words

TITLE_MAX = 70


def problems(ep: Episode) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    pk = ep.package
    for f in ("youtube_title", "description_hi", "thumbnail_text"):
        if not getattr(pk, f).strip():
            errs.append(f"package.{f} is empty")
    if len(pk.youtube_title) >= TITLE_MAX:
        errs.append(f"youtube_title is {len(pk.youtube_title)} chars (must be < {TITLE_MAX})")
    if not 8 <= len(pk.tags) <= 15:
        warns.append(f"{len(pk.tags)} tags (aim for ~10)")
    n = count_words(pk.thumbnail_text)
    if pk.thumbnail_text and not 3 <= n <= 5:
        warns.append(f"thumbnail_text has {n} words (aim for 3–5)")
    if "[VERIFY" in pk.description_hi.upper():
        errs.append("description has an unresolved [VERIFY]")
    return errs, warns


def thumbnail_image(ep: Episode) -> str | None:
    if ep.package.thumbnail_image:
        return ep.package.thumbnail_image
    return next((s.image_file for s in ep.scenes if s.visual.type == "image" and s.image_file), None)


def source_lines(ep: Episode, ep_dir: Path) -> list[str]:
    if ep.package.sources_list:
        return ep.package.sources_list
    files = sorted({ref.split("#", 1)[0] for s in ep.scenes for ref in s.sources})
    return [Path(f).name for f in files]


def is_synthetic(ep: Episode) -> bool:
    if ep.package.synthetic_content is not None:
        return ep.package.synthetic_content
    return any(s.visual.type == "image" for s in ep.scenes)  # realistic generated scenes/people


def write_youtube_md(ep: Episode, ep_dir: Path, disclaimer: str) -> Path:
    pk = ep.package
    title = pk.youtube_title + (" #Shorts" if ep.format == "short" and "#shorts" not in pk.youtube_title.lower() else "")
    src = source_lines(ep, ep_dir)
    desc = [pk.description_hi.strip(), ""]
    if src:
        desc += ["स्रोत:", *[f"• {s}" for s in src], ""]
    desc += [disclaimer]
    synthetic = is_synthetic(ep)
    lines = [
        f"# YouTube upload — {ep.id}", "",
        "## Title", "", title, f"<!-- {len(title)} characters -->", "",
        "## Description", "", *desc, "",
        "## Tags", "", ", ".join(pk.tags), "",
        "## Thumbnail", "", "`render/thumbnail.png`", "",
        "## Upload checklist", "",
        f"- [ ] Format: **{'Short (vertical 9:16)' if ep.format == 'short' else 'regular video (16:9)'}** — file `render/video.mp4`",
        f"- [ ] **Altered or synthetic content: {'YES' if synthetic else 'NO'}**"
        + (" — the video shows realistic AI-generated scenes/people." if synthetic else "")
        + " The narration is an AI voice (not a real person).",
        "- [ ] Audience: not made for kids",
        "- [ ] Language: Hindi; captions are burned in",
        "- [ ] Upload as private/unlisted first, watch once on a phone, then publish",
        "",
    ]
    out = ep_dir / "youtube.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def render_thumbnail(ep: Episode, ep_dir: Path, cfg: dict) -> Path:
    w, h = cfg["package"]["thumbnail_size"][ep.format]
    img = thumbnail_image(ep)
    pub_img = None
    if img:
        pub_img = f"episodes/{ep.id}/{img}"
        link_or_copy(ep_dir / img, PUBLIC / pub_img)
    logo = None
    if BRAND_LOGO.exists():
        link_or_copy(BRAND_LOGO, PUBLIC / "brand" / "logo.png")
        logo = "brand/logo.png"
    props = {"text": ep.package.thumbnail_text, "image": pub_img, "logo": logo, "width": w, "height": h}
    props_path = ep_dir / "render" / "thumbnail-props.json"
    write_json(props_path, props)
    out = ep_dir / "render" / "thumbnail.png"
    res = subprocess.run(["npx", "remotion", "still", "src/index.ts", "Thumbnail", str(out),
                          f"--props={props_path}"], cwd=REMOTION)
    if res.returncode != 0:
        raise RuntimeError("thumbnail render failed")
    return out


def main() -> None:
    p = stage_parser(__doc__)
    args = p.parse_args()
    setup_logging(args.verbose)
    ep_dir = resolve_episode_dir(args.episode)
    cfg = load_config()
    with stage_timer(ep_dir, "package") as run:
        ep = load_episode(ep_dir)
        errs, warns = problems(ep)
        for w in warns:
            run.note(f"warning: {w}")
        if errs:
            raise SystemExit("fill in episode.json `package` first:\n  " + "\n  ".join(errs))
        thumb = render_thumbnail(ep, ep_dir, cfg)
        yt = write_youtube_md(ep, ep_dir, cfg["package"]["disclaimer_hi"])
        run.note(f"{thumb.relative_to(REPO_ROOT)}, {yt.relative_to(REPO_ROOT)} "
                 f"(synthetic disclosure: {'yes' if is_synthetic(ep) else 'no'})")
    print(f"\nCHECKPOINT 3 — review: {thumb.relative_to(REPO_ROOT)}, {yt.relative_to(REPO_ROOT)}, "
          f"{(ep_dir / 'render' / 'video.mp4').relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
