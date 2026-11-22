"""Local image inspection with an open vision-language model (trial, 2026-11-20).

    uv run python -m pipeline.vlm_inspect --eval [--model REPO] [--limit N | --sample N [--seed S]] [--thinking]   # score vs past verdicts
    uv run python -m pipeline.vlm_inspect episodes/<id> [--scene N] [--shot K]             # advisory check

ADVISORY ONLY. This never records an inspection: the official pass/fail still goes through
`images --inspect` after a full-size + zoomed check (CLAUDE.md). It exists to find out whether a local
model can take over part of that work, and to pre-screen shots so obvious failures are retried
before anyone looks.

How a shot is judged (each a separate, narrow question, because small models answer narrow questions
far better than a 13-item checklist):
  full     the whole image + what the shot should show + the narration line: every issue, each rated
           MAJOR (a farmer on a phone would notice, or it teaches the wrong thing) or minor
  identity reference | shot pair for every cast member in the shot, differences rated the same way
  crop×4   optional (--crops): the four 2× zoom quarters. v1 only; far too strict (see docs/ARCHITECTURE.md)
A shot fails if any pass reports a MAJOR issue or its answer can't be read (unsure = fail). Minor issues
are listed but never fail a shot (user decision 2026-11-20: a threshold, not perfection).

--eval rebuilds the labelled set from every episode's log.md: each `inspection PASS|FAIL` line is
matched to the image attempt that was current at that moment (attempt files are kept), and the latest
verdict for an attempt wins. Results stream to samples/vlm-eval/<model>-<prompt version>/results.jsonl
(resumable) and a report goes to report.md beside it.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pipeline.common import REPO_ROOT, load_config

VLM_PROJECT = REPO_ROOT / "vlm"
EPISODES = REPO_ROOT / "episodes"
CAST = REPO_ROOT / "assets" / "cast"
EVAL_DIR = REPO_ROOT / "samples" / "vlm-eval"
DEFAULT_MODEL = "mlx-community/Qwen3.5-9B-4bit"

# ---------------------------------------------------------------- prompts

ROLE = ("You are a strict quality inspector for AI-generated photos used in a farming video for North Indian "
        "farmers. Image generators often make these mistakes: extra, missing or fused fingers; a third hand or a "
        "hand with no arm; one person's arm hidden so he looks one-armed; hands of two people melting together; "
        "impossible knees or feet; a tool with two blades or fused to a bucket; grain or liquid pouring out of a "
        "closed fist, a hand gripping a handle, or an upright bucket; the wrong crop stage; foreign-looking "
        "scenery; readable words. Your job is to FIND such defects. Look carefully and do not assume the image "
        "is fine. Illegible scribbles on sacks, notice boards, charts and held papers are realistic and NOT a "
        "defect; only text a viewer could actually read is a defect. Tiny distant figures don't need limb checks.")

FULL = ROLE + """

What this shot is supposed to show (the image prompt):
{prompt}

The narration line spoken over it (Hindi):
{sentence}

Answer each check about THIS image. Reply with JSON only, no other text:
{{
  "people": <number of clearly visible people>,
  "anatomy": {{"ok": true|false, "issue": "<arms, hands, legs, posture, faces: what is wrong, or empty>"}},
  "separate_people": {{"ok": true|false, "issue": "<bodies or hands of different people merging, or empty>"}},
  "tools_objects": {{"ok": true|false, "issue": "<tool with extra parts, held wrongly, fused objects, floating objects, or empty>"}},
  "action_physics": {{"ok": true|false, "issue": "<poured/thrown/falling material must come from an open hand or a tilted container and land believably; or empty>"}},
  "matches_shot": {{"ok": true|false, "issue": "<does it show what the prompt and narration describe, with the right crop, crop stage and method? or empty>"}},
  "setting": {{"ok": true|false, "issue": "<not rural North India: palm groves, concrete bungalows, foreign look; or empty>"}},
  "readable_text": {{"ok": true|false, "issue": "<only words, numbers or logos a viewer could actually read. Gibberish, scribbles or illegible writing on boards, sacks, charts or papers is ok: true; or empty>"}},
  "verdict": "pass"|"fail",
  "main_problem": "<the most important defect, or empty>"
}}"""

CROP = ROLE + """

This is a 2x zoom of one quarter ({where}) of the image, so you can check small details. People may be cut
off at the edge of this crop; that is NOT a defect. Check every visible person and object:
- every visible hand: count the fingers; look for fused, extra, melted or missing fingers and odd joints
- arms and legs: extra, missing, floating or merged limbs; hands of different people fused together
- feet, faces: deformed or doubled
- tools and containers: extra blades or handles, fused to each other or to the hand
Do NOT report text or writing in this zoom (readable text is judged on the full image; illegible
scribbles on boards, sacks, charts and papers are realistic and fine).

Reply with JSON only, no other text:
{{"visible_people": <number>, "defects": [{{"what": "<defect>", "where": "<where in this crop>"}}], "verdict": "pass"|"fail"}}
Use an empty defects list and "pass" if you find nothing wrong."""

IDENTITY = ROLE + """

LEFT: the approved reference photo of a recurring character. RIGHT: a new shot that must show the SAME
person. Compare face shape, hair and hairline, facial hair, apparent age and build, clothes and their
colours. Anything added that the reference doesn't have (turban, cap, glasses, jewellery, wristwatch) is a
defect unless the shot clearly needs it. If the right image has several people, judge the one that best
matches the reference.

Reply with JSON only, no other text:
{{"same_person": true|false, "differences": ["<difference>", ...], "verdict": "pass"|"fail"}}"""

FULL_KEYS = ["anatomy", "separate_people", "tools_objects", "action_physics", "matches_shot", "setting",
             "readable_text"]

# ---- severity prompts (v2, user decision 2026-11-20): report every issue, rate it major or minor; only a
# MAJOR issue fails a shot. Perfection isn't the bar: Claude and the user already accept small flaws a farmer
# watching on a phone would never notice. The v1 checklist above failed 82% of good shots.
PROMPT_VERSION = "sev2"

SEVERITY = """
Rate every issue you find:
MAJOR = a farmer watching this on a phone for 3 seconds would notice it, or it teaches the wrong thing:
  - a main person with a missing, extra or clearly fused arm, hand or leg, or looking one-armed
  - hands or bodies of two different people merged together
  - poured, thrown or falling material coming from a closed fist, a hand gripping a handle, or an upright
    container, or landing somewhere impossible
  - a tool or container that is clearly broken in shape (two blades, fused to another object or through a hand)
  - the wrong crop, wrong crop stage, wrong method or wrong action for what the shot and narration describe
  - clearly not rural North India (palm groves, coastal or foreign look, modern bungalows)
  - words, numbers or logos a viewer can actually read
MINOR = only visible when looking closely, or doesn't change what the viewer understands:
  - slightly odd fingers or knuckles, a hand partly hidden, a stiff or slightly awkward pose
  - small or distant people with unclear limbs; background objects a bit off
  - lighting, texture, small composition differences from the prompt
  - illegible scribbles on boards, sacks, charts or papers (these are realistic: not even minor, don't list them)
When unsure between major and minor, choose minor unless it is one of the MAJOR cases above."""

FULL_SEV = """You are a quality inspector for AI-generated photos in a farming video for North Indian farmers,
watched mostly on phones. Image generators often make these mistakes: missing, extra or fused hands and
fingers; a person who looks one-armed; hands of two people melting together; a tool fused to a bucket;
grain or liquid pouring from a closed fist or an upright bucket; the wrong crop stage; foreign scenery;
readable words. Look carefully, but judge like an experienced video editor: small flaws nobody notices
on a phone are acceptable.

What this shot is supposed to show (the image prompt):
{prompt}

The narration line spoken over it (Hindi):
{sentence}
""" + SEVERITY + """

Reply with JSON only, no other text:
{{"people": <number of clearly visible people>,
  "issues": [{{"what": "<the issue>", "severity": "major"|"minor"}}],
  "verdict": "pass"|"fail"}}
Verdict is "fail" only if there is at least one MAJOR issue. Use an empty issues list if you see nothing wrong."""

IDENTITY_SEV = """LEFT: the approved reference photo of a recurring character in a farming video. RIGHT: a new shot
that must show the SAME person. If the right image has several people, judge the one that best matches.

MAJOR difference = a viewer would think it is a different person: different face shape or age, different
hair or hairline, beard or moustache added/removed/changed colour, different clothes or clothes colours,
or something added that the reference doesn't have (turban, cap, glasses, jewellery, wristwatch).
MINOR difference = same person under different light, angle, distance or expression: face slightly fuller
or thinner, small shade differences, details too small to see.

Reply with JSON only, no other text:
{{"same_person": true|false, "differences": [{{"what": "<difference>", "severity": "major"|"minor"}}],
  "verdict": "pass"|"fail"}}
Verdict is "fail" only if there is a MAJOR difference."""


# ---------------------------------------------------------------- answers

def parse_json(text: str) -> dict | None:
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    t = re.sub(r"```(?:json)?", "", t)
    start = t.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            esc = (c == "\\") and not esc
            if c == '"' and not esc:
                in_str = False
            elif c != "\\":
                esc = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except ValueError:
                    return None
    return None


_TEXTY = re.compile(r"text|writing|written|letter|word|script|character|sign|label|scribbl|gibberish", re.I)
_ILLEGIBLE = re.compile(r"illegib|gibberish|scribbl|squiggl|unreadable|not readable|not legible|cannot be read|can't be read|"
                        r"nonsens|garbled|meaningless|jumbled|distorted (?:text|letters|writing)|"
                        r"blurr?(?:ed|y) (?:text|letters|writing)|not (?:a )?real (?:text|words|letters)", re.I)


def illegible_text_only(issue: str) -> bool:
    """True when a reported 'defect' is just illegible text, which the rules allow (CLAUDE.md: Images)."""
    return bool(issue) and bool(_TEXTY.search(issue)) and bool(_ILLEGIBLE.search(issue))


def judge(kind: str, answer: dict | None) -> tuple[bool, list[str]]:
    """(failed, reasons) for one pass. An unreadable answer counts as a failure (unsure).
    Complaints that are only about illegible text are dropped: the model raises them despite the prompt."""
    if answer is None:
        return True, [f"{kind}: unreadable answer"]
    reasons = []
    sev_list = answer.get("issues") if "issues" in answer else (
        answer.get("differences") if kind.startswith("identity") and any(
            isinstance(x, dict) for x in answer.get("differences") or []) else None)
    if sev_list is not None:   # v2 severity answer: only MAJOR issues fail
        for d in sev_list:
            what = str(d.get("what") or "").strip() if isinstance(d, dict) else str(d).strip()
            if not what or illegible_text_only(what):
                continue
            sev = str(d.get("severity", "major") if isinstance(d, dict) else "major").lower().strip()
            if not sev:   # blank severity (Ministral lists "... so this is not an issue"): follow the verdict
                sev = "major" if str(answer.get("verdict", "")).lower() == "fail" else "minor"
            reasons.append(f"{kind}: {'MAJOR' if sev != 'minor' else 'minor'}: {what}")
        failed = any(": MAJOR: " in r for r in reasons)
        if kind.startswith("identity") and answer.get("same_person") is False and not failed:
            reasons.append(f"{kind}: MAJOR: not the same person")
            failed = True
        return failed, reasons
    if kind == "full":
        for k in FULL_KEYS:
            v = answer.get(k)
            if isinstance(v, dict) and v.get("ok") is False:
                issue = v.get("issue") or ""
                if k == "readable_text" and illegible_text_only(issue):
                    continue
                reasons.append(f"{k}: {issue or 'not ok'}")
        main = str(answer.get("main_problem") or "")
        if str(answer.get("verdict", "")).lower() == "fail" and not reasons and not illegible_text_only(main):
            reasons.append(f"full: {main or 'verdict fail'}")
    elif kind.startswith("crop"):
        dropped = False
        for d in answer.get("defects") or []:
            what = str(d.get("what") or "").strip() if isinstance(d, dict) else ""
            if not what:
                continue
            if illegible_text_only(what):
                dropped = True
                continue
            reasons.append(f"{kind}: {what} ({d.get('where', '')})")
        if str(answer.get("verdict", "")).lower() == "fail" and not reasons and not dropped:
            reasons.append(f"{kind}: verdict fail")
    elif kind.startswith("identity"):
        if answer.get("same_person") is False or str(answer.get("verdict", "")).lower() == "fail":
            reasons.append(f"{kind}: " + ("; ".join(map(str, answer.get("differences") or [])) or "not the same person"))
    return bool(reasons), reasons


# ---------------------------------------------------------------- shots → jobs

from pipeline.visual_rules import shot_sentence  # noqa: E402  (shared with images --checklist)


def shot_info(ep: dict, scene_id: int, k: int | None) -> dict | None:
    sc = next((s for s in ep.get("scenes", []) if s.get("id") == scene_id), None)
    if not sc:
        return None
    v = sc.get("visual") or {}
    shots = v.get("shots") or []
    if shots:
        sh = shots[(k or 1) - 1] if (k or 1) <= len(shots) else None
        if not sh:
            return None
        return {"prompt": sh.get("image_prompt") or "", "characters": sh.get("characters") or [],
                "sentence": shot_sentence(sc, sh, shots)}
    return {"prompt": v.get("image_prompt") or "", "characters": v.get("characters") or [],
            "sentence": shot_sentence(sc, {}, [])}


def build_jobs(key: str, image: Path, info: dict, work: Path, crops: bool = False) -> list[dict]:
    """full-image severity pass + one identity pass per cast member. The 2x zoom crops (v1 checklist) are
    optional: in the v1 eval they caught nothing the full pass missed and caused most wrong fails."""
    from pipeline.images import write_crops, write_identity_pair   # Pillow lives in the main env
    jobs = [{"id": f"{key}|full", "images": [str(image)],
             "prompt": FULL_SEV.format(prompt=info["prompt"] or "(no prompt recorded)",
                                       sentence=info["sentence"] or "-")}]
    names = {"tl": "top-left", "tr": "top-right", "bl": "bottom-left", "br": "bottom-right"}
    for c in (write_crops(image, work) if crops else []):
        q = c.stem.rsplit("-", 1)[-1]
        jobs.append({"id": f"{key}|crop-{q}", "images": [str(c)], "prompt": CROP.format(where=names.get(q, q))})
    for cid in info["characters"]:
        ref = CAST / cid / "ref.png"
        if ref.exists():
            pair = write_identity_pair(image, ref, work / f"{image.stem}-vs-{cid}.png")
            jobs.append({"id": f"{key}|identity-{cid}", "images": [str(pair)], "prompt": IDENTITY_SEV})
    return jobs


def run_worker(jobs: list[dict], vcfg: dict, on_result) -> None:
    req = {"model": vcfg["model"], "max_tokens": vcfg.get("max_tokens", 1200), "temperature": 0.0,
           "enable_thinking": vcfg.get("thinking", False), "max_pixels": vcfg.get("max_pixels"), "jobs": jobs}
    cmd = ["uv", "run", "--project", str(VLM_PROJECT), "python", str(VLM_PROJECT / "vlm_worker.py")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None, text=True)
    assert proc.stdin and proc.stdout
    proc.stdin.write(json.dumps(req, ensure_ascii=False))
    proc.stdin.close()
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("{"):
            on_result(json.loads(line))
    if proc.wait() != 0:
        raise RuntimeError(f"vlm worker failed (exit {proc.returncode}); see messages above")


def aggregate(results: dict[str, dict]) -> dict[str, dict]:
    """job results → per shot: {failed, reasons, by_pass{kind: failed}, sec}"""
    shots: dict[str, dict] = defaultdict(lambda: {"failed": False, "any": False, "reasons": [], "by_pass": {},
                                                  "sec": 0.0})
    for jid, r in results.items():
        key, kind = jid.rsplit("|", 1)
        ans = None if r.get("error") else parse_json(r.get("text", ""))
        failed, reasons = judge(kind, ans)
        s = shots[key]
        s["by_pass"][kind] = failed
        s["failed"] |= failed
        s["any"] |= failed or bool(reasons)   # any issue at all, minor included (= the "perfection" bar)
        s["reasons"] += reasons
        s["sec"] += r.get("sec") or 0
    return shots


# ---------------------------------------------------------------- labelled set from log.md

LINE_ATTEMPT = re.compile(r"^- scene (\d+)(?: shot (\d+))?: attempt \d+.*→ (\S+\.png)")
LINE_USE = re.compile(r"^- scene (\d+)(?: shot (\d+))?: now using (\S+\.png)")
LINE_INSP = re.compile(r"^- scene (\d+)(?: shot (\d+))?: inspection (PASS|FAIL) \((\S+)\) — (.*)")

FAIL_KINDS = [  # rough grouping of Claude's fail notes, to see which defects a model catches
    ("hands/limbs", r"hand|finger|arm|leg|feet|foot|limb|fist|thumb|fused|one-armed|knee|posture"),
    ("action/physics", r"pour|stream|throw|flow|bucket|spill|float|heap|lands?\b|falling"),
    ("identity", r"identity|face|beard|moustache|turban|cap\b|glasses|different person|not ramesh|not sunita"),
    ("story/crop/practice", r"stage|wheat|ears|crop|narration|practice|lab|kitchen|jar|method|reads as|not a"),
    ("setting", r"palm|bungalow|concrete|foreign|setting"),
    ("text", r"text|readable|letters|word|logo|number"),
]


def fail_kinds(notes: str) -> list[str]:
    n = notes.lower()
    return [k for k, rx in FAIL_KINDS if re.search(rx, n)] or ["other"]


def labelled_set() -> list[dict]:
    items: dict[str, dict] = {}
    for log in sorted(EPISODES.glob("*/log.md")):
        ep_dir = log.parent
        if "phase5-test" in ep_dir.name:
            continue
        try:
            ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        cur: dict[tuple, str] = {}
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LINE_ATTEMPT.match(line) or LINE_USE.match(line)
            if m:
                cur[(int(m.group(1)), int(m.group(2) or 1))] = m.group(3)
                continue
            m = LINE_INSP.match(line)
            if not m:
                continue
            s, k = int(m.group(1)), int(m.group(2) or 1)
            fname = cur.get((s, k))
            img = ep_dir / "images" / fname if fname else None
            if not img or not img.exists():
                continue
            info = shot_info(ep, s, k if m.group(2) else None)
            if not info:
                continue
            key = f"{ep_dir.name}/{fname}"
            items[key] = {"key": key, "episode": ep_dir.name, "scene": s, "shot": k, "image": str(img),
                          "label": m.group(3).lower(), "notes": m.group(5), **info}   # latest verdict wins
    return list(items.values())


# ---------------------------------------------------------------- eval

def model_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model.split("/")[-1])


def sample_shots(data: list[dict], n: int, seed: int = 0) -> list[dict]:
    """A fixed random sample, half fails and half passes (or as many as exist), so a quick first look still
    measures both recall and false fails. Same seed = same shots for every model, so results compare."""
    rng = random.Random(seed)
    fails = sorted((d for d in data if d["label"] == "fail"), key=lambda d: d["key"])
    passes = sorted((d for d in data if d["label"] != "fail"), key=lambda d: d["key"])
    n_fail = min(len(fails), n // 2)
    n_pass = min(len(passes), n - n_fail)
    n_fail = min(len(fails), n - n_pass)
    return rng.sample(fails, n_fail) + rng.sample(passes, n_pass)


def run_eval(vcfg: dict, limit: int | None, keys: list[str] | None, sample: int | None = None,
             seed: int = 0) -> Path:
    data = labelled_set()
    if keys:
        data = [d for d in data if any(k in d["key"] for k in keys)]
    if sample:
        data = sample_shots(data, sample, seed)
    elif limit:   # keep the FAIL/PASS mix: all fails first, then passes, up to limit
        data = sorted(data, key=lambda d: (d["label"] != "fail", d["key"]))[:limit]
    tag = model_slug(vcfg["model"]) + ("-think" if vcfg.get("thinking") else "") + f"-{PROMPT_VERSION}" + (
        "-crops" if vcfg.get("crops") else "")
    out = EVAL_DIR / tag
    out.mkdir(parents=True, exist_ok=True)
    res_path = out / "results.jsonl"
    done: dict[str, dict] = {}
    if res_path.exists():
        for line in res_path.read_text().splitlines():
            r = json.loads(line)
            if not r.get("error"):
                done[r["id"]] = r
    jobs = []
    for d in data:
        # one work folder per episode: attempt file names (scene-01-s1-a1.png) repeat across episodes, and a
        # shared folder let one episode's crops/identity pairs overwrite another's before the model saw them
        for j in build_jobs(d["key"], Path(d["image"]), d, EVAL_DIR / "work" / d["episode"],
                            vcfg.get("crops", False)):
            if j["id"] not in done:
                jobs.append(j)
    n_fail = sum(d["label"] == "fail" for d in data)
    print(f"labelled shots: {len(data)} ({n_fail} fail, {len(data) - n_fail} pass); jobs to run: {len(jobs)} "
          f"(cached {len(done)})", flush=True)
    t0 = time.time()
    if jobs:
        with open(res_path, "a", encoding="utf-8") as f:
            def keep(r):
                done[r["id"]] = r
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
            run_worker(jobs, vcfg, keep)
    report = eval_report(data, {k: v for k, v in done.items() if k.split("|")[0] in {d["key"] for d in data}},
                         vcfg, time.time() - t0)
    name = f"report-sample{sample}-seed{seed}.md" if sample else "report.md"
    (out / name).write_text(report, encoding="utf-8")
    print(report)
    return out / name


def eval_report(data: list[dict], results: dict[str, dict], vcfg: dict, wall: float) -> str:
    shots = aggregate(results)
    combos = {"full only": ["full"], "identity only": ["identity"], "crops only": ["crop-tl", "crop-tr", "crop-bl", "crop-br"],
              "full + crops": ["full", "crop-tl", "crop-tr", "crop-bl", "crop-br"], "all passes": None,
              "all passes, minor issues also fail (perfection)": "any"}
    lines = [f"# Local inspection eval — {vcfg['model']}{' (thinking)' if vcfg.get('thinking') else ''}", "",
             f"{len(data)} labelled shots (Claude's latest verdict per attempt). "
             f"Run time this session {wall / 60:.1f} min.", "",
             "| passes used | fails caught (recall) | passes wrongly failed | agreement |", "|---|---|---|---|"]
    for name, kinds in combos.items():
        tp = fn = fp = tn = 0
        for d in data:
            s = shots.get(d["key"])
            if not s:
                continue
            bp = s["by_pass"]
            if not any(k in bp or (k == "identity" and any(b.startswith("identity") for b in bp))
                       for k in (kinds if isinstance(kinds, list) else ["full"])):
                continue   # this run didn't ask these questions
            failed = s["any"] if kinds == "any" else any(v for k, v in bp.items() if kinds is None or k in kinds or
                         (kinds is not None and k.startswith("identity") and "identity" in kinds))
            if d["label"] == "fail":
                tp += failed
                fn += not failed
            else:
                fp += failed
                tn += not failed
        n = tp + fn + fp + tn
        if not n:
            lines.append(f"| {name} | not asked in this run | | |")
            continue
        lines.append(f"| {name} | {tp}/{tp + fn} ({100 * tp / max(tp + fn, 1):.0f}%) | {fp}/{fp + tn} "
                     f"({100 * fp / max(fp + tn, 1):.0f}%) | {100 * (tp + tn) / max(n, 1):.0f}% |")
    # recall per kind of defect (all passes)
    by_kind = defaultdict(lambda: [0, 0])
    for d in data:
        if d["label"] == "fail" and d["key"] in shots:
            for k in fail_kinds(d["notes"]):
                by_kind[k][1] += 1
                by_kind[k][0] += shots[d["key"]]["failed"]
    lines += ["", "Fails caught by kind of defect (all passes; a shot can have several kinds):", ""]
    lines += [f"- {k}: {a}/{b}" for k, (a, b) in sorted(by_kind.items())]
    secs = [s["sec"] for k, s in shots.items() if k in {d['key'] for d in data}]
    mems = [r.get("peak_mem_gb") or 0 for r in results.values()]
    unread = sum(1 for r in results.values() if r.get("error") or parse_json(r.get("text", "")) is None)
    lines += ["", f"Per shot: {sum(secs) / max(len(secs), 1):.0f} s on average (all passes); peak memory "
              f"{max(mems or [0]):.1f} GB; unreadable answers {unread}/{len(results)}.", "",
              "## Every shot", "", "| shot | Claude | local | Claude's notes | local reasons |", "|---|---|---|---|---|"]
    for d in sorted(data, key=lambda d: (d["label"], d["key"])):
        s = shots.get(d["key"])
        if not s:
            continue
        loc = "fail" if s["failed"] else "pass"
        mark = "" if loc == d["label"] else " ⚠"
        why = "; ".join(s["reasons"])[:400].replace("|", "/")
        lines.append(f"| {d['key']} | {d['label']} | {loc}{mark} | {d['notes'][:220].replace('|', '/')} | {why} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- advisory check of an episode

def check_episode(ep_dir: Path, vcfg: dict, scenes: list[int], shot: int | None) -> None:
    ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    work = ep_dir / "images" / "inspect"
    jobs, keys = [], {}
    for sc in ep.get("scenes", []):
        if scenes and sc["id"] not in scenes:
            continue
        for k, sh in enumerate((sc.get("visual") or {}).get("shots") or [], start=1):
            if shot and k != shot or not sh.get("image_file") or not (ep_dir / sh["image_file"]).exists():
                continue
            key = f"scene {sc['id']} shot {k}"
            keys[key] = sh
            jobs += build_jobs(key, ep_dir / sh["image_file"], shot_info(ep, sc["id"], k), work,
                               vcfg.get("crops", False))
    if not jobs:
        raise SystemExit("no shot images to check")
    results: dict[str, dict] = {}
    run_worker(jobs, vcfg, lambda r: results.__setitem__(r["id"], r))
    shots = aggregate(results)
    out = {}
    for key, s in shots.items():
        out[key] = {"local_verdict": "fail" if s["failed"] else "pass", "reasons": s["reasons"],
                    "official": (keys[key].get("inspection") or {}).get("passed"), "model": vcfg["model"]}
        flag = "FAIL" if s["failed"] else "pass"
        off = out[key]["official"]
        print(f"{key}: local {flag}  (official: {'pass' if off else 'fail' if off is False else 'not inspected'})")
        for r in s["reasons"]:
            print(f"    - {r}")
    (work / "vlm-check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nadvisory only — record the real inspection with images --inspect. Saved {work / 'vlm-check.json'}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode", nargs="?")
    p.add_argument("--eval", action="store_true", help="score the model against past inspection verdicts")
    p.add_argument("--model", help="mlx-vlm model repo (default: config images.vlm_inspect.model)")
    p.add_argument("--thinking", action="store_true", help="let the model reason before answering (slower)")
    p.add_argument("--limit", type=int, help="eval: at most N shots (all fails first)")
    p.add_argument("--sample", type=int, help="eval: a fixed random N shots, half fails and half passes")
    p.add_argument("--seed", type=int, default=0, help="eval: seed for --sample (same seed = same shots)")
    p.add_argument("--only", nargs="*", help="eval: only shots whose key contains one of these strings")
    p.add_argument("--crops", action="store_true", help="also ask about the four 2x zoom crops (v1; strict)")
    p.add_argument("--scene", type=int, action="append", default=[])
    p.add_argument("--shot", type=int)
    a = p.parse_args(argv)
    vcfg = {"model": DEFAULT_MODEL, "max_tokens": 1200, "max_pixels": 1_600_000,
            **(load_config().get("images", {}).get("vlm_inspect") or {})}
    if a.model:
        vcfg["model"] = a.model
    if a.crops:
        vcfg["crops"] = True
    if a.thinking:
        vcfg["thinking"], vcfg["max_tokens"] = True, max(vcfg.get("max_tokens", 1200), 6000)
    if a.eval:
        run_eval(vcfg, a.limit, a.only, a.sample, a.seed)
    elif a.episode:
        check_episode(REPO_ROOT / a.episode, vcfg, a.scene, a.shot)
    else:
        p.error("give an episode folder or --eval")


if __name__ == "__main__":
    sys.exit(main())
