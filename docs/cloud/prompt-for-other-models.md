# Prompt: cloud architecture for the AgriGate Hindi video pipeline

Copy everything between the two `=====` lines into each model (ChatGPT, Gemini, Grok, DeepSeek, …). Turn on web search / deep research if the model has it. The fixed output format at the end makes the answers comparable side by side with `docs/cloud/proposal-claude.md`, which follows the same headings. A comparison rubric is at the bottom of this file (not part of the prompt).

=====

## Your role and task

You are a senior cloud and ML-infrastructure architect. Research current services, pricing and model support (as of late 2026), then design how to run the video pipeline described below **entirely in the cloud, end to end**, so that nothing depends on the operator's laptop. Today it runs on one MacBook. I want a concrete, buildable architecture: which service runs each job, how jobs are connected and triggered, where every piece of data lives, how messages and state flow, how human approvals work, what it costs, and how to migrate in safe steps.

Be specific (service names, instance or GPU types, regions, limits), cite the documentation or pricing pages you relied on with their dates, and say clearly where you are unsure. Don't propose anything you haven't checked supports the model or tool in question.

## 1. What the system does

AgriGate produces **Hindi educational YouTube videos for farmers in North India** (mostly watched on phones). An AI narrator explains a topic (soil testing, fertiliser use, sowing…) over AI-generated photorealistic stills with slow pan/zoom (Ken Burns), simple animated graphics (title cards, key points, big numbers) and word-timed Hindi captions with the spoken word highlighted.

- Formats: `long` = 16:9, 3–5 min, ~20–25 scenes; `short` = 9:16 YouTube Short, 30–60 s.
- Volume now: one long video every 2–3 days (~10–15/month), plus some Shorts. Plan for growth to ~60 videos/month.
- Operated by a small team (assume 1–2 people, no dedicated DevOps engineer). Cost-sensitive, but quality and accuracy matter more than cost.
- The company already uses **AWS** for its other products. Staying mostly on AWS is preferred, but other providers (serverless GPU platforms, render services, model APIs) are fine where they are clearly better. Justify any second vendor.

## 2. Current pipeline, stage by stage

An episode is produced **interactively in a Claude Code session** (Anthropic's coding agent). Claude follows "skills" (markdown instructions) to write the script, run each stage as a Python CLI, look at every generated image, and stop at human checkpoints. Heavy media work runs locally on a **MacBook Air M5, 16 GB unified memory, fanless, Apple Silicon (no CUDA)**, one heavy job at a time.

| # | Stage | What happens | Tool / model today | Compute today (4-min episode) |
|---|---|---|---|---|
| 0 | New episode | Create folder, `brief.md` (topic, crop, region, season, format), `sources/` (official PDFs/pages the facts must come from; Claude fetches government/ICAR documents when none are supplied) | Python CLI + Claude | seconds |
| 1 | Script | Claude writes Hindi narration per scene (hook → problem → explain → steps → mistakes → recap → CTA), cites a source file per factual scene, marks anything unsupported `[VERIFY: …]`. Delivery markup (`|` breath, `{slow|warm|firm|question}`) | Claude (LLM) | minutes of LLM time |
| 1a | Text normalize | Display text → spoken text: Hindi number words, units, currency, colloquial fractions, pronunciation overrides | pure Python | <1 s |
| 1b | Validate | Schema + `[VERIFY]` check + sources exist + length targets + stage-completeness gates; the **only** way status advances | pure Python | <1 s |
| — | **CHECKPOINT 1** | A human approves the script | human | — |
| 2 | Narration | Split into sentences; **N takes per sentence** (5–6) with different seeds; each take transcribed by Whisper and scored (character error vs script, pitch range, gaps, voice-identity drift); best take picked; takes trimmed, joined with controlled pauses, one episode-wide loudness gain to −14 LUFS | TTS: **Maya2 Native** (male; Qwen3-1.7B-based LM + Kyutai **Mimi** codec, Apache-2.0 / Mimi CC-BY-4.0, run via mlx-audio) and **Veena** (female; Llama-style LM emitting **SNAC** tokens, Apache-2.0, run by our own mlx-lm worker), both on **MLX** (Apple-only). ASR: **Whisper large-v3-turbo via mlx-whisper**. ffmpeg for audio | Measured: **~28 min** for a 3.7-min episode with Maya2 (5 takes per sentence, ~1× realtime, incl. scoring). Veena runs ~4.7× realtime with 6 takes, so roughly 1.5–2 h |
| 2a | Word timing | Whisper word timestamps on the final audio, aligned to the script letter-by-letter, snapped to silences; drives caption timing, word highlight and when graphic points appear | mlx-whisper + Python | ~30 s |
| 3 | Cast | Recurring synthetic characters (main farmer, lab technician) with a human-approved reference image, so the same face appears in every shot | image model | one-off |
| 3a | Images | Each image scene has 1–3 **shots**. Claude writes a structured scene spec → linted positive-only prompt (the model has no negative prompt). Shots with cast members use **edit mode with the reference image**. Up to 3 attempts per shot, deterministic seeds, every attempt kept | **FLUX.2 [klein] 4B, 4-bit, via mflux (MLX)**, ~20 s/image, ~40–90 s in edit mode. A blind bake-off is under way: **FLUX.3 Image Klein q8 leads (33/36 pass)**, Z-Image q6 10/12; larger models don't fit 16 GB | Measured on the latest episode: **24 shots, 49 attempts**, ~16 min for the first pass, ~30 min in total |
| 3b | **Image inspection (mandatory gate)** | Every image is checked at full size + 2× zoomed crops + a side-by-side vs the character reference: limbs, hands, fingers, fused people, tool grip, **action physics** (poured material comes from an open hand or tilted container), crop stage and farming practice match the narration, no readable text, Indian rural setting, identity match. Verdict + notes recorded, bound to the image's SHA-1; the pipeline refuses to continue until every image passes. Local open VLMs were tested and rejected (best, Ministral 3 14B: 16/20 failures caught but 26% of good shots wrongly failed) | **Claude (vision)** reads the PNGs | the real bottleneck: LLM/human attention |
| 3c | Graphics | Claude fills template props (KeyPoints, BigNumber, TitleCard); cue times computed from word timings | Python | <1 s |
| 4 | Draft render | 540p draft | **Remotion 4.0.545** (React/TypeScript, headless Chrome), bundled Devanagari font, assets synced into `public/` | ~1.75 min |
| — | **CHECKPOINT 2** | A human watches the draft; notes are applied scene by scene, often several re-renders | human | — |
| 5 | Final render | 1080p H.264/AAC | Remotion | ~1.6 min |
| 6 | Review | Contact sheets (frame every 2 s), loudness, duration, black-frame/freeze checks → `review.md`; Claude inspects every sheet | ffmpeg + Pillow + Claude | <1 min + LLM |
| 7 | Package | Thumbnail (Remotion still), YouTube title/description/tags, sources, synthetic-content disclosure → `youtube.md` | Remotion + Python + Claude | seconds |
| — | **CHECKPOINT 3** | A human approves; upload is manual today (YouTube Data API upload is planned) | human | — |

There is also a local web **control room** (Python stdlib server): episode status rail, job queue (run/stop/retry stages), live progress and ETA, per-episode cost (Claude tokens + local electricity), a blind image-rating page for the bake-off.

Planned next (design for these, don't build them yet): background music with ducking, Shorts re-cut from long episodes, short image-to-video clips (1–2 s, e.g. Wan or LTX-Video), YouTube upload as private/scheduled after checkpoint 3, YouTube Analytics feedback into topic planning, a topic backlog driven by the crop calendar, and eventually unattended runs (the original plan said LangGraph with interrupts at the three checkpoints).

## 3. Data and state model

- **`episode.json` is the single source of truth** per episode (strict pydantic schema, `extra="forbid"`; mirrored as TypeScript types for Remotion). Every stage reads it and writes its results back; writes are atomic and re-validated. It holds scenes, narration (display + spoken), per-sentence audio segments and per-word timings, captions, visual shots (prompt, seed, attempt, file, reference hash, inspection record with SHA-1), graphics props, sources per scene, status, package metadata.
- Status machine: `draft → script_approved → narrated → visuals_ready → draft_rendered → final_rendered → reviewed → packaged`, advanced only through `validate --set-status`, which runs every gate up to the target level.
- Episode folder: `brief.md`, `sources/` (PDFs + README of URLs and conflicts), `script.md`, `episode.json`, `audio/` (every take + metrics, segment picks, final scene WAVs, word timings), `images/` (every attempt + current pick + inspection crops), `render/` (draft.mp4, video.mp4, thumbnail), `review/`, `youtube.md`, `log.md` (append-only: every stage's duration, outcome, checkpoint decisions). About 3 GB for ~11 episodes so far (mostly audio takes and image attempts); final videos are ~400 MB each.
- Shared assets: cast references, brand, prompt-rule library (`visual_rules.yaml`, updated after every failed inspection), pronunciation fixes, config, fonts.
- Stages are **idempotent and per-item**: skip existing outputs unless `--force`; `--scene N` redoes one scene; caches keyed by content hashes (TTS take = hash of text+style+seed).
- Every backend is a small function with a fixed contract (e.g. `synthesize(text, voice_cfg, out_path) -> duration_sec`), selected in `config.yaml`, and the model workers already run as **subprocesses with JSON in/out** in isolated Python environments. The design goal from day one was "a stage can move to AWS or an API without touching the others".

## 4. Non-negotiables your design must preserve

1. **Accuracy over automation.** Facts only from files in `sources/`; nothing passes the script stage while any `[VERIFY` remains.
2. **Three human checkpoints** (script, draft video, final + package) that **cannot be skipped by automation**. Ideally enforced by permissions, not just convention: the automated agent must be unable to approve its own work. Approvals should be easy from a phone (watch the draft, listen to audio, approve or leave notes).
3. **Every generated image inspected** by a strong vision model (currently Claude) at full size plus zoomed crops, with the verdict bound to the image hash; humans can override. Open VLMs may pre-screen but never decide.
4. **Licenses:** no non-commercial or research-only models or libraries. Revenue-capped community licenses (e.g. FLUX.3 Klein) are acceptable. Remotion needs a paid company license for commercial use (budget it). No cloning of a real person's voice; no real faces.
5. **Reproducibility and audit:** every attempt, take, seed, verdict and checkpoint decision is kept and attributable.
6. **`episode.json` stays the contract** between stages (it may move from a file to object storage or a database, but stages keep the same schema).

## 5. Questions to answer

1. **Compute per job.** For each stage, which service should run it and why (serverless function, container task, serverless GPU, managed render service, LLM API)? Include GPU type for TTS, Whisper and image generation, and the cold-start, quota and scale-to-zero implications at our volume.
2. **Porting off Apple MLX.** Maya2, Veena, Whisper and FLUX run via MLX today. What is the CUDA/cloud equivalent for each (e.g. transformers/vLLM/SGLang for the TTS LMs plus their Mimi and SNAC decoders, faster-whisper/WhisperX, diffusers/ComfyUI for FLUX.2/3 klein incl. reference-image edit mode)? What changes in quality or behaviour should we re-test, and how? Once the 16 GB limit is gone, which **commercially licensed** image models become worth testing?
3. **Orchestration.** What runs the flow: AWS Step Functions, Temporal, LangGraph (self-hosted or platform), Prefect/Dagster, Inngest, or something else? How are long human waits (hours to days) handled? How do retries, per-scene reruns and fan-out (e.g. 40 shots × attempts in parallel, sentences × takes) work?
4. **Where Claude fits.** Today Claude is an interactive agent with file and shell access. In the cloud, how should its judgement steps (script writing with source fetching, image inspection and prompt fixing, contact-sheet review, metadata) run: Claude API calls inside workflow steps, the Claude Agent SDK in a container, Claude Code on the web/remote sessions, or a mix? How do we keep an **interactive** mode (operator chats with the agent about an episode) and also allow **unattended** runs that pause at checkpoints?
5. **Storage and state.** Where does each artefact live (object storage layout, database for status/jobs/index, versioning, lifecycle/retention, CDN for previews)? How do we keep `episode.json` writes atomic and validated when many parallel workers finish at once (optimistic concurrency, per-item result files + a merge step, a database, …)?
6. **Messaging and events.** How do stages hand off (direct invocation, queues, event bus, webhooks)? Draw the message flow for one episode from brief to upload, including checkpoint waits and an inspection failure → retry loop.
7. **Rendering.** Remotion Lambda vs Remotion on containers vs alternatives: cost, limits, fonts, assets from object storage, draft vs final.
8. **Control room and approvals.** How to host the dashboard (auth, roles: operator vs approver), show live progress, play audio and video, and capture checkpoint decisions with identity and timestamp; notifications (email, WhatsApp, Slack).
9. **Security and operations.** Secrets (Anthropic, Hugging Face gated models, YouTube OAuth), IAM least privilege, infrastructure as code, CI/CD, logging, cost tracking per episode and per stage, budgets/alerts.
10. **Cost.** Monthly estimate at 12 and at 60 long episodes/month, split into fixed and per-episode, and by stage. Say which line dominates.
11. **Migration.** A phased plan where each phase is usable on its own, says what still runs on the Mac during the transition, and has an acceptance test (e.g. A/B the cloud TTS against the Mac on the same sentences).
12. **Alternatives you rejected** and why (e.g. a rented cloud Mac running everything as-is, a single always-on GPU VM, fully managed media APIs).

## 6. Required output format (keep these headings so answers can be compared)

A. **Summary recommendation** (≤10 lines)
B. **Architecture diagram** (Mermaid or ASCII)
C. **Service per job** table: job | service | GPU/size | why | rejected alternatives | est. cost per episode
D. **Orchestration, Claude's role and human checkpoints**
E. **Data and storage** (layout, `episode.json` concurrency, versioning, retention)
F. **Messaging and event flow** for one episode (sequence diagram), including a failed image inspection and a rejected draft
G. **Porting the Mac-only parts** (per model: cloud runtime, risks, how to verify parity)
H. **Security, licenses and operations**
I. **Cost model** (12 and 60 episodes/month; fixed vs per-episode; dominant cost)
J. **Phased migration plan** with acceptance tests
K. **Risks and open questions** for us
L. **Sources consulted** (URL + date) and confidence level for key claims

=====

## Comparison rubric (for you, not part of the prompt)

Score each answer 1–5 on:

| Criterion | What good looks like |
|---|---|
| Fidelity to the pipeline | Notices MLX is Apple-only, the N-takes + Whisper scoring loop, edit mode with references, the SHA-1 inspection gate, the strict single-writer `episode.json` |
| Checkpoints enforced | Approval cannot be done by the agent (IAM/roles), not only by convention; phone-friendly review |
| Claude's role | Concrete plan for both interactive and unattended modes; inspection still by a strong vision model |
| Concurrency | Has an answer for many parallel workers writing results into one `episode.json` |
| Right-sized | Scale-to-zero for ~12 episodes/month; no always-on GPU; no Kubernetes for a 1–2 person team |
| Licenses | Doesn't suggest non-commercial models; budgets the Remotion company license |
| Cost realism | Separates fixed vs per-episode; identifies the dominant cost; cites pricing pages |
| Migration | Small, independently useful phases with parity tests (audio and image A/B) |
| Evidence | Cites current docs; flags uncertainty instead of inventing limits |
