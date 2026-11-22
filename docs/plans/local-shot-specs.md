# Plan: local shot specs (no hand-written image prompts)

Status: P1 done 2026-11-22 (see `docs/ARCHITECTURE.md` §7.6e, D36). P2–P5 not started. Open decisions at the end.

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

### P2. Local LLM env
- New isolated `llm/` env (`mlx-lm`), worker with JSON in/out, called as a subprocess like `tts-mlx/` and `asr/`.
- Runs before the image stage, never at the same time as FLUX (16 GB).
- Backend settings in `config.yaml: shot_specs` (model, max repair rounds, temperature). Record the
  dependency and model license in `docs/licenses.md`.

### P3. New stage `pipeline.shot_specs episodes/<id> [--scene N] [--force]`
- **Shot plan, done by code:** one shot per sentence from `audio.segments`, merging short ones, within
  `config.yaml: shots` (2.5–9 s), with wide → medium → close-up variety. The LLM only chooses what each
  shot shows and which cast members appear (at most 2).
- **Spec writer, done by the LLM:**
  - context: the sentence, its neighbours, the episode topic, the cast list, and the `visual_rules`
    phrases whose narration keywords match (e.g. कटाई → `{stage:harvested_stubble}`);
  - examples: 3–4 approved bake-off specs picked by similarity (urea broadcast, soil sampling, lab);
  - output validated by code; the stage writes the spec and rendered prompt into `episode.json`,
    wrapped in `stage_timer`.
- **Revise after a failed inspection:** `--revise --scene N --shot K` gives the LLM the fail notes and the
  old spec and gets a new spec. This replaces Claude rewriting prompts.

### P4. Choose the model by measuring
1. **Text check (no images):** run the 3 cached models on 63 shots (39 bake-off + 24 v3). Score: specs
   passing the checks within 3 rounds, required phrases present, right action and crop stage for the
   sentence (compared with the approved specs), seconds per shot.
2. **Image check (~1.5 h of generation):** generate all 24 v3 shots from the best model's specs and inspect
   them. Target: first-try passes near the 85–90% of Claude-written specs, well above v3's 58%.
- Record results in `docs/timings.md` and a short report.

### P5. Wire it in
- Dashboard (`dashboard/flow.py`): "Shot specs (local LLM)" step, marked "This Mac".
- Skills: `visuals` and `make-episode` run the stage instead of Claude writing prompts.
- Docs: `docs/ARCHITECTURE.md`, `docs/licenses.md`, `docs/timings.md`, CLAUDE.md commands.

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

## Open decisions (user)

1. Shot planning by code, LLM chooses only content (recommended), or let the LLM plan the shots too?
2. Should the user see specs/prompts at a checkpoint before images, or go straight from narration to images?
3. Order: P1 → P2 + P3 → P4 → P5 (recommended).
