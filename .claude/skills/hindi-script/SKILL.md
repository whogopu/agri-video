---
name: hindi-script
description: Write the Hindi narration script (script.md + episode.json scenes) for an AgriGate episode from brief.md and sources/. Use for the script stage and for applying script edits at checkpoint 1.
---

# hindi-script (draft)

## Inputs
`episodes/<id>/brief.md` and every file in `episodes/<id>/sources/`. Read all sources fully before writing.

## Rules
- Simple spoken Hindi (बोलचाल की हिंदी). Use farmer terms: यूरिया, DAP, स्प्रे, बीज दर. Short sentences.
- Tone: experienced कृषि सलाहकार; respectful, practical, no hype, no fear.
- Structure: hook (≤10 s) → problem → explain → steps → mistakes → recap → cta. CTA line = `config.yaml: script.cta_hi`.
- Check `episode.json: format`. **long** (16:9): 3–5 min, full structure. **short** (9:16 Short): 30–60 s, one practical tip: hook → the tip → one mistake to avoid → CTA. Keep on-screen text and graphic text even shorter (narrow frame).
- Word target depends on the voice pace (`episode.json: voice.wpm`; Rohit ~171 wpm → ~510–855 words long, ~85–170 short). `validate` prints the target. Scenes of 6–12 s (~17–34 words at Rohit pace), one idea per scene.
- **Facts only from sources.** Every dose/quantity/date/price/scheme/product → list the backing file in the scene's `sources` (e.g. `sources/advisory.pdf#p3`). Anything unsupported → `[VERIFY: what needs checking]`. Never guess.
- Pesticides/chemicals: add a line to read the label and consult the local KVK or agriculture officer. No brand names unless asked.
- `on_screen_text`: optional, 1–4 words.
- Suggest a `visual.type` per scene (graphic for numbers/lists/titles). The visuals stage finalizes it.

## Writing for the ear (delivery markup)
Narration is spoken one sentence at a time, so write how a good कृषि सलाहकार talks: short sentences, a question to the farmer, a beat before the key fact, the key number repeated in the recap. Light markup in `narration_display` shapes the delivery (stripped from captions and word counts; `pipeline/prosody.py`):
- `||` long pause: after the opening question, after "अब कुछ आम गलतियां।", before the key point.
- `|` short breath inside a long sentence. Use rarely; each part should still be ≥ 3 words, because Parler handles very short text badly.
- `{slow}` `{warm}` `{firm}` `{question}` at the start of a sentence: override the automatic style (questions → question, numbers → slow, CTA → warm, mistakes → firm). Usually not needed.
- Don't put markup inside a number, unit or the CTA line. `text_normalize` keeps the markup in `narration_spoken`; both must have the same marks.

## Steps
1. Fill `episode.json` scenes (`narration_display`, `purpose`, `on_screen_text`, `visual.type`, `sources`) and `title_hi`.
2. Build `narration_spoken`: `uv run python -m pipeline.text_normalize episodes/<id>` (numbers → Hindi words, units, `pronunciation.yaml`). Read the output; fix odd readings with a `pronunciation.yaml` entry and rerun with `--force`.
3. Write `script.md`: a table of scene | purpose | Hindi narration | visual idea | sources, plus total words and estimated length.
4. `uv run python -m pipeline.validate episodes/<id>` and fix errors.
5. **CHECKPOINT 1:** show `script.md`, list any `[VERIFY]` items, wait. After approval: `validate --set-status script_approved`.
