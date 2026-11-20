---
name: make-episode
description: Produce one AgriGate Hindi farmer video end to end — script, narration, visuals, draft/final render, review, package — stopping at the three human checkpoints. Use when the user asks to make, continue, or resume an episode in episodes/<id>.
---

# make-episode

Orchestrate the stages in order. Read `episodes/<id>/episode.json` `status` first and resume from there.

New episode: ask for the topic, the sources, the **format** (long 16:9 3–5 min, or short 9:16 30–60 s) and the **voice** (maya_vasant by default, or veena_varun) if the user hasn't given them. Then run `uv run python -m pipeline.new_episode <slug> --format … --voice …`. Visuals are generated images + graphics; B-roll is used only if the library has usable clips.

**Cast (recurring characters).** The people on screen are the channel's recurring characters (`uv run python -m pipeline.cast list`; रमेश जी is the main farmer), so faces stay consistent. Visual only: the narration stays an informative explainer addressed to the viewer and does not name them or tell their story. The script stage sets `episode.json: cast`. A **new** character needs a casting step before visuals: `cast new` → `cast candidates` → inspect each candidate → `cast sheet` → the **user picks** the face → `cast approve <id> N`. Never run `cast approve` without the user naming the candidate. An approved reference is reused in every later episode; don't change it unless the user asks (that makes every older shot of the character stale).

| Step | Skill / command | Ends with status |
|---|---|---|
| 1 Script | `hindi-script` | draft → **CHECKPOINT 1** → `script_approved` |
| 2 Narration | `narration` | `narrated` |
| 3 Visuals | `visuals` | `visuals_ready` |
| 4 Draft render | `render` (`--draft`) | `draft_rendered` → **CHECKPOINT 2** |
| 5 Final render | `render` | `final_rendered` |
| 6 Review | `review` | `reviewed` |
| 7 Package | `package` | `packaged` → **CHECKPOINT 3** |

## Rules

- **Never skip a checkpoint.** "Just do everything" is not permission. Only skip one if the user explicitly names it for this episode, and note that in `log.md`.
- At each checkpoint, tell the user exactly which file to open and what to look for, then stop and wait.
- Advance status only with `uv run python -m pipeline.validate episodes/<id> --set-status <status>`. If it fails, fix the cause; don't edit status by hand.
- If a stage fails, fix or retry **that stage only** (use `--scene N` for one scene). Don't rerun earlier stages unless their outputs are wrong.
- Run heavy stages (narration, images, render) one at a time.
- Applying checkpoint notes: change only the scenes mentioned, rerun downstream stages with `--scene N --force`.
