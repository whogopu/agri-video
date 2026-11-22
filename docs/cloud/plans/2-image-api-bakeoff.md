# Plan 2: Image API bake-off

**Goal:** find out whether a hosted image model beats FLUX.3 Klein q8 (the 2026-11-21 local bake-off winner) on our real shots, especially the hard parts: hands, poured material, costumes, and cast identity across shots. If one does, images need no GPU in the cloud.

**Candidates** (verify prices at run time):
- **Nano Banana Pro** (Gemini 3 Pro Image; ~$0.134/img; up to 14 reference images, keeps several people consistent).
- **Nano Banana 2.x** (cheaper Gemini image model).
- **GPT-Image 2.x** (OpenAI; edit with references).
- **FLUX.2 [pro] / [flex]** via the BFL API (~$0.03–0.06/img; multi-reference).
- **Seedream 4.5** (ByteDance; via fal.ai or BytePlus).
- **FLUX.3 Klein** hosted (BFL API or fal) as the control: same model as local, removes the quantisation question.

## Steps

1. **API runner in `pipeline/bakeoff.py`.** Today `build_cmd()` builds an mflux command. Add a model kind `api` in `config.yaml: bakeoff.models` with `provider` (`gemini` | `openai` | `bfl` | `fal`), `model`, and options (size, quality). Add `pipeline/image_apis.py` with one function per provider: `generate(prompt, refs, w, h, seed, opts, out) -> {usd, sec}`. Pass seed where the API accepts it; otherwise record `seed: null`.
   - API calls are light, so skip `wait_for_quiet()` / cooldown for `api` models, but keep sequential calls per provider to respect rate limits.
   - Cast shots: send the head-crop references (`assets/cast/<id>/ref_head.png`) plus the full reference as the provider's reference images, led by `cast.reference_preamble`.
2. **Prompts.** Use the same scene specs (`bakeoff/shots.yaml`) and the same positive-only prompts from `prompts()`. Do not tune per vendor in round 1 (fairness). Round 2 may add a vendor-specific preamble for the top two.
3. **Aspect.** Our size is 1344×768 (16:9). APIs offer fixed sizes; request 16:9 and record the returned size. Shorts (9:16) tested in round 2.
4. **Run round 1.** All 12 bake-off shots + the cast shots, 1 seed each, every candidate. Cost estimate: ~20 shots × 6 models ≈ 120 images ≈ $8–16.
5. **Inspect.** Claude inspects every image exactly as for production (full size + crops, `images.inspection_checklist`, `action:` note, identity side-by-side for cast shots) and records via `bakeoff.record_inspection`. One image at a time, never from a grid.
6. **Blind rating.** `bakeoff.blind()` then the user rates on `/bakeoff` (dashboard; ask the user to restart it after code changes).
7. **Report.** `bakeoff.report()` extended with columns: provider, $/image, seconds/image, pass rate, identity pass rate, blind score. Write the summary into `bakeoff/report.md` and the decision into `docs/cloud/image-bakeoff.md`.
8. **Visual rules.** Any failure pattern specific to a provider goes into `assets/visual_rules.yaml` notes (§7.6c), tagged by model.

## Acceptance

- A hosted model is adopted only if its inspection pass rate ≥ FLUX.3 Klein q8's on the same shots, its cast identity pass rate is at least as good, and the user's blind ratings prefer it or tie.
- Its terms allow commercial use of outputs and are recorded in `docs/licenses.md` (Hosted APIs section).
- Readable-text rule still holds: no readable text in generated images (Gemini and GPT-Image like to draw legible text; check signs and bags closely).

## Also measure

Cost per finished episode = attempts per passing shot × $/image + Claude inspection cost per attempt. A model with a higher first-attempt pass rate can be cheaper overall even at a higher $/image, because Claude inspection ($10.65 on v3) dominates.
