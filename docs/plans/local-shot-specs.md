# Plan: local shot specs (no hand-written image prompts)

Status: P1 done 2026-11-22 (commit d75f780, branch `local-shot-specs`; `docs/ARCHITECTURE.md` §7.6e, D36).
P2 done 2026-11-22: the existing `vlm/` env writes specs text-only, no new env (results below). P3–P5 in progress. Decisions recorded at the end; "Order of work for the next session" is the handoff.

## Goal

Today Claude (cloud) reads the Hindi narration, plans the shots and hand-writes a free-text `image_prompt`
for every shot. Move this to a local model so image prompts are produced on this Mac, and make them rich
enough that FLUX.3 passes more images on the first try, so inspection has less to reject.

## Where we are

- Production shots carry a free-text `image_prompt` written by Claude (e.g. v3 scene 3 in
  `episodes/2026-11-20-mitti-ki-jaanch-v3/episode.json`).
- `pipeline/scene_spec.py` already defines a **scene spec**: a structured description of one shot (framing,
  setting, crop stage, people with each hand's job, objects with what holds them up, poured/thrown
  material from source to landing, contacts). `lint()` rejects incomplete specs; `render()` turns a spec
  into one prompt in code. It is used only by the bake-off (`bakeoff/shots.yaml`), not by `pipeline.images`.
- Evidence: with Claude-written specs, FLUX.3 Klein q8 passed 35/39 (bake-off), against 14/24 first-try
  passes (58%, 40 generations) on v3's free-text prompts with the older FLUX.2 klein 4B. No production
  episode has used specs, library tokens or FLUX.3 yet.
- Local LLMs already in the HF cache: Ministral 3 14B 4-bit, Qwen3.5 9B 4-bit, Gemma 4 E4B 4-bit.

## Approach

The local LLM fills in the **spec** and never writes the prompt; code turns the spec into the prompt.

```
Hindi sentence + topic + cast + matching visual_rules phrases + approved example specs
   → local LLM (mlx-lm) → spec (JSON)
   → code checks: scene_spec.lint, visual_rules lint (no negations, risky words),
     must-show phrases present, cast clothes/face not contradicted
       ↳ errors go back to the LLM to fix, up to 3 rounds
   → scene_spec.render() → prompt → FLUX.3 (unchanged)
```

Why: small local models are unreliable at long free text but good at filling slots when code rejects gaps.
The usual failures (closed fist, upright bucket pouring, wrong crop stage, third hand) are exactly what
the spec checks catch before any image is generated.

## Phases

### P1. Specs in production (no LLM yet) — done 2026-11-22
- Add an optional `spec` to `Shot` in `pipeline/schema.py` (and the mirror in `remotion/src/types.ts`).
- `pipeline.images`: a shot with a spec gets its prompt from `scene_spec.render()`; free-text
  `image_prompt` keeps working. Store the rendered prompt on the shot so inspection sees what was sent.
- Move lint/render code so production and the bake-off share it. Cast shots: spec people with `cast:`
  skip face/clothes (the cast preamble supplies them).
- Useful on its own: Claude-written specs improve production right away.

### P2. Local LLM worker
- **Try the existing `vlm/` env first** (mlx-vlm 0.7.12, already used by `pipeline/vlm_inspect.py`): the
  cached Ministral 3 14B and Qwen3.5 9B are vision-language models that mlx-vlm already loads, and
  `vlm/vlm_worker.py` accepts jobs with `images: []`. Text-only spec writing may need no new env or
  dependency. Only if that fails (no JSON mode, too slow, wrong chat template) add an isolated `llm/` env
  with `mlx-lm`, worker called as a subprocess with JSON in/out like `asr/` and `tts-mlx/`, and record it
  in `docs/licenses.md`.
- Worker contract: request `{model, max_tokens, temperature, jobs: [{id, system, prompt}]}` on stdin; one
  JSON line per job on stdout `{id, text, sec, prompt_tokens, gen_tokens, peak_mem_gb}`. Model loaded once
  per request. Parsing and judging stay in the main env, so prompts can change without touching the env.
- Never runs at the same time as FLUX, TTS, Whisper or a render (16 GB). Reuse the bake-off's "wait while
  another heavy job runs" check (`pipeline/bakeoff.py`).
- Settings in `config.yaml: shot_specs`: `model`, `max_tokens`, `temperature` (0–0.3), `max_repair_rounds: 3`,
  `examples: 4`, `max_cast_per_shot: 2`.

**P2 result (2026-11-22):** `vlm/vlm_worker.py` with `images: []` works unchanged for both cached models: valid
JSON (Ministral wraps it in a ```json fence), one v3 sentence + 2 example specs → Ministral 3 14B 60 s / 9.2 GB,
Qwen3.5 9B 41 s / 7.1 GB. No `llm/` env, no new dependency. The worker takes one `prompt` per job, so the
main env joins system + user text; a repair round is one more worker request (model load 2–8 s), batched over all
shots still failing. Typical faults seen already: clothes/age on cast people, an extra cast member who doesn't
belong in the place, contradictory hands. Those are code checks (P3).

### P3. New stage `pipeline.shot_specs` + shot-plan checkpoint
```
uv run python -m pipeline.shot_specs episodes/<id> [--scene N] [--force]    # plan shots + write specs
uv run python -m pipeline.shot_specs episodes/<id> --scene N --shot K --revise ["user note"]
uv run python -m pipeline.shot_specs episodes/<id> --plan-only               # shot plan by code, no LLM
```
Runs after `narrated`, on scenes with `visual.type == "image"` (the script stage suggests the type; graphics
and B-roll scenes are untouched). Wrapped in `stage_timer`, idempotent and per-scene like every stage:
existing specs are kept unless `--force`.

**1. Shot plan, fully by code (decision 1).** No human or LLM step:
- from `audio.segments`: one shot per sentence; merge a sentence shorter than `shots.min_shot_sec` into its
  neighbour; a scene keeps 1–3 shots; each shot 2.5–9 s (`config.yaml: shots`, the same limits `validate`
  warns on). Sets `at_segment`.
- framing per shot by rule: first shot of a scene wide or medium-wide (where we are), then medium (what is
  done), then close-up (hands, soil, card); never the same framing twice in a row. The framing string
  comes from a small table in config, not from the LLM.
- deterministic: same narration timings → same plan. Unit-tested on v3's segments.

**2. Spec writer, local LLM, content only.** Per shot, one job:
- context: the shot's Hindi sentence(s) + the neighbouring sentences, the scene `purpose`, episode
  `title_hi`/topic, the cast list (`id`, role, gender; never face/clothes, the reference supplies them), the
  framing chosen by code, and the `visual_rules` phrases matched for this sentence (`prompt_hints`,
  `must_show` from `pipeline/visual_rules.py`, e.g. कटाई → `{stage:harvested_stubble}`);
- examples: the 3–4 most similar approved specs from `bakeoff/shots.yaml` (pick by keyword overlap with the
  sentence: broadcast / sampling / lab / report / sacks …);
- the LLM returns the spec as JSON (teaches, setting, crop_stage, people with `cast:` and both hands,
  objects, flows, contacts, inspector_notes). Framing is overwritten with the code's value;
- code checks, errors sent back for up to 3 repair rounds: `scene_spec.lint`, rendered-prompt lint
  (`visual_rules.lint`: no negations, risky words as warnings), must-show items present in the spec text,
  cast ids ⊂ `episode.cast` and ≤ 2 per shot, cast people carry no clothes/age/build. Still failing after
  3 rounds → shot left without a spec and listed as "needs Claude/user" (never a silent fallback).
- writes `spec` and `characters` into `episode.json` (rendering stays in `images.shot_prompt`, from P1).

**3. Shot-plan checkpoint, the user sees specs and prompts (decision 2).** A new human checkpoint between
narration and images (user decision 2026-11-22):
- new status `shots_approved` between `narrated` and `visuals_ready`
  (`pipeline/schema.py: Status`, validate gates, dashboard flow, `make-episode` skill, CLAUDE.md status flow
  and checkpoint list: four checkpoints now);
- the stage writes `review/shots.md`: per scene and shot, the timing, the Hindi sentence, the framing, a
  one-line summary (`teaches`, who, what each hand does), the full rendered prompt (`images --dry-run`
  text) and any warnings;
- dashboard: a "Shot plan" review page showing the same per shot, with approve / note-per-shot;
- the user's notes go to `--revise --scene N --shot K "note"` (LLM rewrites that spec with the note);
  then `validate --set-status shots_approved`, which requires every image shot to have a spec or
  image_prompt that lints clean;
- `pipeline.images` refuses to generate episode shots while status < `shots_approved`
  (one-off mode and `--dry-run` still work).

**4. Revise after a failed inspection.** `--revise --scene N --shot K` with no note reads the shot's fail
`inspection.notes`, sends old spec + notes to the LLM, writes the new spec. Then `images --retry`.
**User decision 2026-11-22:** the first automatic revision of a shot goes straight to `images --retry` (marked
"revised after inspection" in `review/shots.md` and `log.md`); if that shot fails inspection again, its next
revision waits for the user's approval of that shot (`shot_specs --approve --scene N --shot K`) before
`images` will regenerate it.

### P4. Choose the model by measuring
1. **Text check (no images):** run the cached models (Ministral 3 14B, Qwen3.5 9B; Gemma only if its terms
   allow commercial use) on 63 shots (39 bake-off + 24 v3). Score: specs passing the checks within 3
   rounds, must-show phrases present, right action and crop stage for the sentence (compared with the
   approved specs), seconds per shot, peak memory.
2. **Image check (~1.5 h of generation):** generate all 24 v3 shots from the best model's specs into a copy
   of the v3 episode (never overwrite v3's images) and inspect them. Target: first-try passes near the
   85–90% of Claude-written specs, well above v3's 58%.
- Record results in `docs/timings.md` and a short report (`samples/shot-specs-eval/report.md`).

### P5. Wire it in
- Dashboard (`dashboard/flow.py`): "Shot plan (code)" + "Shot specs (local LLM)" steps marked "This Mac",
  then "Checkpoint: shot plan" (kind `human`).
- Skills: `visuals` and `make-episode` run `shot_specs`, stop at the shot-plan checkpoint, and use
  `--revise` after failed inspections instead of Claude writing prompts. Claude still decides graphics vs
  image, inspects every image, and updates `assets/visual_rules.yaml` after failures.
- Docs: `docs/ARCHITECTURE.md` (stage, status, decision row), `docs/licenses.md`, `docs/timings.md`,
  CLAUDE.md commands, status flow and checkpoint list.

### Order of work for the next session
1. P2: text-only smoke test of `vlm/vlm_worker.py` with one bake-off sentence → JSON spec; time it.
2. P3 step 1 (shot plan by code) with tests on v3 segments.
3. P3 step 2 (spec writer + repair loop) on 2–3 v3 scenes, `--dry-run` prompts reviewed by Claude.
4. P3 step 3 (status `shots_approved`, `review/shots.md`, images gate) with tests.
5. P4 text check → pick model → image check (ask the user before the 1.5 h generation run).
6. P3 step 4 (`--revise`), then P5.
Run `uv run pytest -q` and `cd remotion && npx tsc --noEmit` after each step; commit per step on branch
`local-shot-specs`.

## Limits

- **Inspection stays with Claude in this phase**: P4 needs a trusted verdict to measure against. Less
  inspection work comes from fewer failures and retries. Local inspection is a separate phase (see the
  2026-11-21 VLM trial: best local model wrongly failed 30% of good shots).
- **Updating `assets/visual_rules.yaml` after failures** stays manual (user or Claude). Later the local LLM
  could propose a rule change for the user to approve.
- **Speed (estimate, to be measured in P4):** a 14B model at roughly 30–60 s per shot, so 15–25 min per
  episode before images.
- **Licenses:** Ministral 3 and Qwen3.5 are Apache-2.0. Gemma has its own terms, to be checked before it
  counts as a candidate. No downloads needed unless P4 shows the cached models fall short (ask before > 6 GB).

## Decisions (user, 2026-11-22)

1. **Shot planning by code**, locally automated with minimal human intervention; the LLM chooses only the
   content of each shot.
2. **The user sees the specs and prompts** at a new shot-plan checkpoint before any image is generated.
3. Order: P1 (done) → P2 + P3 → P4 → P5.

4. Automatic revisions after a failed inspection: the first goes through without re-approval; a second
   revision of the same shot needs the user's approval (P3 step 4).
