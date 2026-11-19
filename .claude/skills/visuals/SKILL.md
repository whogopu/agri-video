---
name: visuals
description: Choose and produce the visual for each scene of an AgriGate episode — B-roll from the library, generated images (mflux), or graphics (TitleCard/KeyPoints/BigNumber). Use after narration, or to redo a scene's visual.
---

# visuals

Requires status `narrated` (scene durations are known).

## Choosing
Default: **generated images + graphics**. B-roll is optional; the library is usually empty.
- First run `uv run python -m pipeline.broll check`. If it shows no complete clips, skip B-roll entirely and don't mention it.
- **B-roll** (only if usable clips exist) when a library clip really fits (`uv run python -m pipeline.broll list --tag <crop>`). Only use clips that `broll check` reports as complete; they need a license. Set `broll_id`, `in_sec` and `out_sec`. The segment should be at least the scene's `audio.duration_sec` + 0.35 s; Remotion slows a shorter one down to at most 0.5×. Prefer `usable_segments`. Never reuse the same clip segment in one episode.
- **Image** for anything that needs to show a real scene (most scenes).
- **Graphic** for numbers, lists and titles. Hindi text, short.

## Format
Shorts (`format: short`) are 9:16. Images are generated portrait (`config.yaml: formats.short.image_size`). Prefer B-roll whose subject stays in the centre third, since landscape clips are center-cropped. Keep the key subject in the upper two thirds; the Shorts UI covers the bottom.

## Images
```bash
uv run python -m pipeline.images episodes/<id>                                   # all image scenes (~18 s each)
uv run python -m pipeline.images episodes/<id> --scene N --retry [--prompt "..."] # next attempt, new seed
```
- **Two people and one object** (a hand-over, a handshake, showing a report): describe the hands apart, e.g. "the farmer holds the bag by its drawstring; the officer's open palm waits just below it, a clear gap between their hands". Where you can, show one person's hands at a time.
- For labs, offices, KVKs and shops, let the model add notice boards and charts. For reports and cards, ask for "a printed report sheet with tables" and check that it stays illegible. Don't ask for bare walls, blank paper or "no posters". Only reject text you can actually read, or large brand/logo signs.
- Write `visual.image_prompt` in English and be concrete: who (Indian farmer, clothing), crop **and its stage** (e.g. "harvested field with short rice stubble"), the action, the tool (khurpi, hand trowel, backpack sprayer), the setting (mud-brick village, Punjab wheat field) and the light. Don't put words or numbers in the prompt. The style suffix and the seed are added automatically.
- Model: FLUX.2 klein 4B (q4). It follows concrete prompts well; vague prompts drift (a "khurpi" may become a spade).
- **Inspect every image. This is mandatory, and validate enforces it:**
  1. Open the image at full size: one image per look, never a grid.
  2. Run `uv run python -m pipeline.images episodes/<id> --scene N --crops` and open the 4 zoomed quarters in `images/inspect/`.
  3. Go **person by person** through `config.yaml: images.inspection_checklist` (`images --checklist` prints it):
     - **2 arms, 2 hands, both visible**, each hand attached to its own arm. A person whose second arm is hidden behind the body or a saree looks one-armed and fails, unless the frame edge crops them or it's a hands-only close-up. In prompts, say what both hands are doing ("holding the bag with both hands", "receiving it with both hands cupped").
     - **separate people**: where two people touch or pass something, zoom in on the contact point. Each hand must be complete and separate, with a gap or the object between them, and you must be able to follow every hand back to its owner's arm. Fused hands fail.
     - **5 fingers** on every visible hand; no fused or extra fingers
     - **2 legs, 2 feet**
     - **posture** physically possible (joints bend the right way, balanced stance)
     - **dress** right for rural India and the role, not merging into skin or objects
     - **tools and objects**: one blade and one handle, held correctly, nothing fused together
     - natural faces, no stray limbs, Indian context, right crop and stage
     - **text:** nothing readable (words, numbers, brands, logos). Illegible text where real objects have it is **realistic. Keep it:** notice boards, wall charts and posters in labs, offices and KVKs; labels on sacks and bags; **documents people hold** (a soil report should look printed, with table lines, not blank). Don't prompt for "bare walls", "blank paper" or "seen from the back".
  4. Record it: `--scene N --inspect pass --notes "farmer: 2 arms/2 hands/5+5 fingers/2 legs, squat OK, kurta OK; spade single handle in soil"`, or `--inspect fail --notes "..."` and then `--retry`.
  The notes must say what you counted. A regenerated image clears its inspection automatically.
- If a person isn't essential to the scene, prefer a prompt without people: fewer limbs, fewer failures. Name the clothing and the grip in the prompt ("holding the single wooden handle with both hands").
- All attempts are kept as `images/scene-XX-aN.png`; `scene-XX.png` is the current pick. After 3 attempts (`images.max_attempts`) the stage flags the scene in `log.md` instead. Tell the user and suggest B-roll or a graphic. Use `--retry --extra-attempt` only when the user explicitly asks for another try.

Finish with `uv run python -m pipeline.validate episodes/<id> --set-status visuals_ready`. It checks image files, seeds, clip licenses and in/out ranges, and that no B-roll segment is reused.
