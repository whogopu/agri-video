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
  - Graphics appear **on cue** (`pipeline/cues.py`): each KeyPoints point slides in when the narrator starts on it, a BigNumber's number pops when it is spoken (its label shows first). Cues are found automatically from the point's words (in order; numbers match their spoken form). Write points with words the narration actually uses. If `validate` warns that a point didn't match, or a cue lands on the wrong word, set `props.cues` (KeyPoints: one phrase or null per point) or `props.cue` (BigNumber), copied from `narration_display`.

## Format
Shorts (`format: short`) are 9:16. Images are generated portrait (`config.yaml: formats.short.image_size`). Prefer B-roll whose subject stays in the centre third, since landscape clips are center-cropped. Keep the key subject in the upper two thirds; the Shorts UI covers the bottom.

## Shots: several pictures per scene
An image scene holds `visual.shots` (1–3). Each shot starts at a narration **segment** (sentence) via `at_segment`; the cut lands in the pause before that sentence and the next picture dissolves in (6 frames). Plan from `audio.segments` (narration is done by now):
- one sentence ≈ one shot; each shot 2.5–9 s on screen (`config.yaml: shots`; validate warns outside). Merge very short sentences into one shot.
- vary the framing: wide (where we are) → medium (what he does) → close-up (hands, soil, the card). Never two near-identical shots in a row.
- `characters`: cast ids visible in the shot. Shots without people (soil close-up, fertilizer sacks) leave it empty and generate faster.
```json
"visual": {"type": "image", "shots": [
  {"at_segment": 0, "characters": ["ramesh"], "image_prompt": "Ramesh walks into his harvested wheat field ..."},
  {"at_segment": 1, "characters": [], "image_prompt": "Close-up of dry cracked brown soil ..."}]}
```

## Cast shots (consistent characters)
- Shots with `characters` run FLUX.2 klein **edit mode** with the characters' approved reference images (`assets/cast/<id>/ref.png`). `images.py` adds the preamble automatically: "Ramesh is the man in reference image 1: keep exactly his face … and his clothes (…); his short grey-black hair uncovered, bare wrists, bare fingers." (`accessories` in `character.json`, positive wording). So in `image_prompt` just call him by name and describe the action, pose, framing and setting. Don't describe his face or clothes again, and don't contradict them.
- ~40 s per shot with one character, ~90 s with two. At most 2 characters per shot.
- Two characters: keep them apart (counter between them, one placing, one waiting). Hand-overs remain the riskiest shot.

## Images
```bash
uv run python -m pipeline.images episodes/<id>                                     # all shots of all image scenes
uv run python -m pipeline.images episodes/<id> --scene N --shot K --retry [--prompt "..."]  # next attempt, new seed
uv run python -m pipeline.images episodes/<id> --scene N --shot K --crops         # crops + reference|shot pair
uv run python -m pipeline.images episodes/<id> --scene N --shot K --inspect pass --notes "...; identity: ..."
```
- **Two people and one object** (a hand-over, a handshake, showing a report): describe the hands apart, e.g. "the farmer holds the bag by its drawstring; the officer's open palm waits just below it, a clear gap between their hands". Where you can, show one person's hands at a time.
- For labs, offices, KVKs and shops, let the model add notice boards and charts. For reports and cards, ask for "a printed report sheet with tables" and check that it stays illegible. Don't ask for bare walls, blank paper or "no posters". Only reject text you can actually read, or large brand/logo signs.
## Writing image prompts (`assets/visual_rules.yaml`)
Model: FLUX.2 klein 4B (q4), guidance 1.0, so **there is no negative prompt**. Naming a thing tends to put it in the picture: in the 2026-11-20 A/B, "no palm trees" drew a palm and "no standing crop anywhere" drew rows of seedlings, while the positive rewrites drew neither. Most past failures contained exactly what the prompt said "no" to (palms, wristwatch, a second bucket, water, steam).
1. **Describe only what is there.** `images.py` lints every prompt before generating and rejects *no / not / without / nothing / instead of / avoid*. Say "bare wrists", not "no watch"; "a flat field of bare soil with short cut stubble stumps", not "no standing crop"; "clear still liquid", not "no steam".
2. **Use the library.** Before writing a shot, run `uv run python -m pipeline.images episodes/<id> --scene N --shot K --checklist`: it prints the shot's narration sentence, what its picture must show, and which tokens to use (e.g. `after_harvest: {stage:harvested_stubble}`). Write tokens like `{stage:harvested_stubble}`, `{setting:north_field_bg}`, `{prop:steel_bucket_clean}`, `{action:broadcast_open_hand}` in the prompt; they expand to tested phrases. `uv run python -m pipeline.visual_rules --list` shows them all with their test status; `--lint "..."` checks a prompt.
3. **Five layers, in this order:** (1) framing and camera ("Medium shot from the side at waist height"); (2) who and what **both hands** do; (3) props, with grip and state (clean, dry, tilted); (4) setting and crop stage; (5) light. Framing goes first because klein tends to ignore it at the end. Don't describe a cast member's face or clothes, and don't put words or numbers on things. The style suffix and the seed are added automatically.
4. Count words ("one single bucket") didn't change counts in tests. Describe the scene instead, and check counts at inspection.
   - **Two different objects, one per hand** → klein copies the stronger one ("bucket in his right hand and a spade in his left" drew two buckets). Give him one object, or put the second inside or next to the first.
   - **A resting hand must have something to rest on, on its own side.** "Her left hand resting on the bench" with the bench on her right side drew a third hand. Place the bench in front of her ("both hands on the bench in front of her"), or let the free arm hang relaxed.
   - **Jewellery keeps coming back.** Rings appeared on Ramesh in 2 of 5 cast shots and on Sunita in 1 of 2, even with "bare fingers" in the preamble. Zoom on every hand for rings, bangles and watches. Small rings and bangles are **minor** (user decision 2026-11-21): list them in the note and pass. A wristwatch or anything large still fails. Ramesh's approved `ref.png` may itself show a faint ring on his right hand, which would explain why "bare fingers" loses; Sunita gets extra gold bangles and a bangle on her right wrist although her reference has one thin bangle on the left.
5. **Warnings** (`risky_words`) aren't blocking but mean something: "wheat" alone draws a standing crop with ears, "khurpi" draws a garden trowel, "jar" reads as a kitchen.
6. **New phrases:** if a shot needs a phrase the library doesn't have and several episodes will use it, add it with `tested: null` and run a 3-seed A/B (old vs new wording, same seeds, one-off `images --prompt ... --out ... --seed`) before relying on it. Record the result in `tested:`.
- **Inspect every image. This is mandatory, and validate enforces it:**
  1. Open the image at full size: one image per look, never a grid.
  2. Run `uv run python -m pipeline.images episodes/<id> --scene N --shot K --crops` and open the 4 zoomed quarters in `images/inspect/` (plus the reference|shot pair for cast shots).
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
     - **action & physics (every shot; user rule 2026-11-20):** in a zoomed crop, trace every poured, thrown, sprayed or falling material back to its source: an open throwing hand, the mouth of a tilted container, a nozzle. Fail if it comes out of a closed fist, a hand gripping a handle, an upright bucket or thin air; if the container angle doesn't match the flow; if broadcast khaad lands as one heap; if a hand posed to throw throws nothing; if anything floats or passes through a solid. The notes must contain `action: ...` (`action: static` when nothing moves); `images --inspect pass` refuses notes without it.
     - **narration & good practice:** the picture shows what the sentence says and teaches the right farming: crop and stage, method, tool, a plausible quantity, clean equipment where the script says clean. A picture that teaches the wrong thing fails even if every hand is perfect. If the model can't draw a step (e.g. quartering a soil sample), don't settle for a misleading picture: use a graphic or drop the shot.
     - **identity (cast shots):** open `images/inspect/<shot>-vs-<id>.png` (reference left, shot right). Same face, hairline, facial hair, age, build; same clothes and colours; nothing added (turban, cap, glasses, wristwatch). Small rings and bangles are minor: note, don't fail. Another face fails even if the image is otherwise good. The notes must contain the word "identity".
  4. Check the shot's **must show** items (`--checklist` with `--scene N --shot K`; also printed after generating). They come from the prompt's library tokens and the narration keywords (e.g. कटाई → bare stubble, no standing crop).
  5. Record it: `--scene N --shot K --inspect pass --notes "farmer: 2 arms/2 hands/5+5 fingers/2 legs, squat OK, kurta OK; spade single handle in soil; action: blade cuts into soil, loosened soil beside the pit"`, or `--inspect fail --notes "..."` and then `--retry`.
  The notes must say what you counted. A regenerated image clears its inspection automatically.
  6. **After every FAIL, update `assets/visual_rules.yaml`** so the mistake doesn't come back next episode: fix the phrase that drew it, add a `risky_words` entry for the word that caused it, or add a `narration` rule (keyword → must show) for the check that caught it. Say in the fail notes what you changed (`rules: ...`).
- If a person isn't essential to the scene, prefer a prompt without people: fewer limbs, fewer failures. Name the clothing and the grip in the prompt ("holding the single wooden handle with both hands").
- All attempts are kept as `images/scene-XX-sK-aN.png`; `scene-XX-sK.png` is the current pick. After 3 attempts per shot (`images.max_attempts`) the stage flags the scene in `log.md` instead. Tell the user and suggest B-roll or a graphic. Use `--retry --extra-attempt` only when the user explicitly asks for another try.

Finish with `uv run python -m pipeline.validate episodes/<id> --set-status visuals_ready`. It checks image files, seeds, clip licenses and in/out ranges, and that no B-roll segment is reused.
