# Cloud architecture: four answers compared, and the frontier/SaaS option

> **Audience:** the AgriGate team deciding how to move the video pipeline to the cloud.
> **Inputs:** `responses/gemini.md`, `responses/claude.md` (a separate Claude session without web access), `responses/chatgpt.md`, and my own `proposal-claude.md`. Claims were checked against this repo, the dashboard's measured costs and a web check on 2026-11-22 (sources at the end).

---

## 1. Bottom line

1. **On the base architecture, all four answers agree, so treat it as settled:**
   - AWS in Mumbai (ap-south-1): Step Functions with one workflow run per episode, and the workflow pausing until a person approves (`waitForTaskToken`).
   - S3 (versioned) for files, DynamoDB for status, Cognito for logins, Remotion Lambda for rendering.
   - Workers never write `episode.json` themselves; one merge step does, using S3 conditional writes so two writes can't clash.
   - Approvals are enforced by IAM permissions: no machine role can approve, only a person in the approvers group.
2. **They disagree mainly on where the GPU work runs** (Modal vs AWS Batch) and on how much Claude costs. Your preference for frontier models and SaaS can make the GPU question disappear. If hosted APIs match today's quality for **voice** and **images**, no GPU is needed at all. That removes the biggest risk all four answers flag: porting Maya2, Veena and FLUX from Apple's MLX to CUDA and proving quality didn't drop.
3. **Claude cost dominates every design.** Measured on v3 (interactive, Opus): **$22.76 for the episode, $10.65 of it image inspection.** Hosting and render costs are small next to it.
4. **Recommended next step:** two short bake-offs with API keys, each about a day of work and under ~$30 in API fees:
   - Hindi voice: hosted TTS vs Maya2.
   - Images: frontier image APIs vs FLUX.3 Klein, using the existing bake-off harness and blind rating page.

   Then decide between a no-GPU architecture and one with a GPU vendor.

## 2. Scores (rubric from `prompt-for-other-models.md`, 1–5)

| Criterion | Gemini | Claude (other session) | ChatGPT | Mine |
|---|---|---|---|---|
| Fidelity to the pipeline | 3 | 4 | **5** | 4 |
| Checkpoints enforced | **5** | **5** | **5** | 4 |
| Claude's role (interactive + unattended) | 4 | **5** | 4 | 4 |
| Concurrency on `episode.json` | **5** | **5** | **5** | 4 |
| Right-sized for 1–2 people | **5** | **5** | 3 | **5** |
| Licences | 4 | 3 | **5** | 3 |
| Cost realism | 2 | **4** | **4** | **4** |
| Migration plan | 4 | **5** | 4 | 4 |
| Evidence | 3 | 2 | **5** | 3 |
| **Total / 45** | **35** | **38** | **40** | **35** |

### What each got right, and where each is wrong

**ChatGPT (40): the most rigorous.**
- **Right:**
  - It's the only one that caught that Maya2 is Qwen3 + Mimi, not Llama + SNAC. Those answers were written from the uncorrected prompt.
  - It flags Veena's model card for showing a "proprietary" tag alongside Apache-2.0.
  - Licence facts are correct: Remotion is free for organisations of up to 3 people; FLUX.3 Klein needs a deal above the cap.
  - Approvals are bound to the exact revision, a stale review page can't approve, and pressing approve twice can't advance the workflow twice.
  - It prices BFL's hosted klein at ~$0.014 per image.
- **Weak:**
  - It puts GPUs on AWS Batch. Each job then waits several minutes for a machine to start, and the network setup (private subnets, VPC endpoints) adds $13–28/month and more to operate.
  - Its GPU estimate ($2–4 per episode) is the highest of the four.
  - It dismisses Claude Code on the web as a production runtime. That's fair for unattended runs, but it leaves out a cheap interactive option.

**Claude, other session (38): the best plan for operating it, but no evidence.**
- **Right:**
  - The **MCP server for interactive Claude Code** is the cleanest way to keep the chat-driven workflow. The tools would be `run_stage`, `get_media_url` and `record_inspection`, with no approve tool, so a Claude session on any device drives the cloud.
  - Approvals are bound to the `episode.json` version.
  - The permission boundary has explicit denies, so a mis-scoped policy can't grant approval.
  - Phases are small, each with failure tests. Cost per episode ($6–14) is close to measured.
- **Weak:**
  - Nothing was checked online; it says so itself.
  - It assumes a paid Remotion licence, which may not be needed.
  - It's unsure about FLUX.3 and Maya2 licences.

**Gemini (35): clean design, unrealistic numbers.**
- **Right:**
  - Approvals are bound to a SHA-256 of the reviewed file: editing after approval re-locks the gate.
  - An SQS queue serialises the merges, and the merge writes conditionally.
  - Bedrock has Claude in India.
  - It found the Remotion ≤3-person free licence.
- **Wrong:**
  - Inspection at **$0.38 per episode** against $10.65 measured.
  - All narration in ~95 s on one L4 GPU.
  - Total **$0.85 per episode**.
  - The old Maya2 description and ~40 shots per episode.
  - Its costs are off by roughly 10×, so don't budget from them.

**Mine (35).**
- **Right:** the same base architecture; Modal for GPUs; the pragmatic order of building interactive mode first.
- **Wrong:**
  - I told you to buy the Remotion company licence. It's **free if AgriGate, as a whole organisation, has ≤3 people**; otherwise it's the Automators plan at $0.01 per render with a $100/month minimum.
  - Relying on Claude Code on the web for interactive work is weaker than the other session's MCP server.

### Facts now confirmed (they change the budget)

| Topic | Verified position |
|---|---|
| Remotion | Free for an individual or an organisation of up to 3 people, automation included. Above that, **Automators: $0.01 per render, $100/month minimum.** Lambda renders count; previews don't. Headcount is the whole organisation, not the video team. |
| FLUX.3 Image Klein | FLUX Kommunity License: **free commercial use below US$5M gross annual revenue including affiliates**. Above that, a self-hosting deal with BFL with no published price, or their paid API. |
| Claude prices (`config.yaml`) | Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per million input/output tokens. Claude is on Bedrock in India (Gemini and ChatGPT both cite the 2026-09-29 announcement). |
| Measured Claude per episode | v3 $22.76 (inspection $10.65); pilot $4.19; v2 $6.62; first demo $24.84. The interactive figures include rework and re-inspection. |

## 3. The frontier / SaaS option, stage by stage

The test for each stage: can a hosted model or service do it **at today's quality**, inside the rules (sources, three checkpoints, **every image inspected**, no voice cloning, commercial terms)?

| Stage | Today | Frontier / SaaS candidates (indicative prices, verify) | My call |
|---|---|---|---|
| Script, sources, image inspection, review, metadata | Claude Code (interactive) | **Claude API** for inspection, review and metadata (structured JSON verdicts). **Claude Managed Agents** for the script and agent loops: an Anthropic-hosted sandbox, token rates plus **$0.08 per active session-hour**. It replaces the self-run Fargate container all four answers proposed, but it's only on the direct Claude API, not Bedrock. | **Adopt.** Already frontier. Managed Agents removes one thing to run. |
| Hindi narration (TTS) | Maya2 Native and Veena on the Mac, 5–6 takes per sentence, Whisper-scored | **Sarvam Bulbul** (Hindi-first, Indian, about ₹20 per 10k characters). **ElevenLabs v3** (~$80 per million characters). **Gemini TTS** (token-priced, style set by prompt). A 4-min episode is ~3.5k characters × 6 takes ≈ 21k characters, about **$0.25–2 per episode**. | **Test first.** You chose Maya2 after a 5-model listening test, so a hosted voice must win the same test. The take-picking loop works with APIs unchanged; only the backend changes. |
| Take scoring + word timing (Whisper) | mlx-whisper large-v3-turbo | **The same Whisper large-v3-turbo as a hosted API** (e.g. Groq; check word timestamps and prompt support), which means no change in behaviour. Others: ElevenLabs Scribe, Soniox (~$0.10/h), Sarvam, Deepgram. Pitch metrics run on CPU in Lambda. | **Adopt the hosted Whisper**, after re-running the word-timing measurement from ARCHITECTURE §7.4a. |
| Images + cast consistency | FLUX.2/3 Klein on the Mac, reference images for cast shots, positive-only prompts | **Nano Banana Pro** ($0.134 per image; up to 14 reference images and up to 5 consistent people). **Nano Banana 2.1** (~$0.03–0.05). **GPT-Image 2.x** (token-priced, ~$0.03–0.13). **FLUX.2 [pro]/klein via the BFL API** ($0.014–0.045 plus reference megapixels). **Seedream 4.5** (~$0.04 on fal). About 50 attempts per episode comes to **~$1–7**. | **Test first; best chance of a big win.** Frontier image models follow long prompts, understand "without", and are built for multi-reference character consistency. That targets your two hardest problems: hands and physics, and costume or identity swaps. A higher pass rate also cuts Claude inspection cost. |
| Render | Remotion on the Mac | **Remotion Lambda** (all four agree). Template-video SaaS (Creatomate, Shotstack) would lose the word highlight, cues and Devanagari control. | **Adopt Remotion Lambda.** |
| Image-to-video (planned) | — | Kling, Veo and others via fal at ~$0.07–0.14 per second; 1–2 s clips cost cents. | Later, behind a flag. |
| End-to-end video SaaS (InVideo AI, Pictory, Fliki, HeyGen) | — | Script-to-video in one tool | **Reject.** None can enforce source-only facts and `[VERIFY]`, the per-image inspection gate, recurring cast references or your three checkpoints. Useful only as a benchmark for look and pacing. |

### What changes if both bake-offs go to the APIs

- **No GPU vendor and no CUDA porting.** That removes phases 2–4 of every plan (weeks of work), the MLX→CUDA parity risk, and the Modal-vs-Batch decision.
- **Architecture:** AWS (Step Functions, Lambda, S3, DynamoDB, Cognito, CloudFront, Remotion Lambda) + Anthropic (Claude API and Managed Agents) + one image API + one TTS API + hosted Whisper. Model APIs are called from Lambda, with keys in Secrets Manager.
- **Fewer vendors** if wanted: **fal.ai** sells many image and video models behind one API and bill, which suits testing. In production, going direct to Google, BFL or OpenAI gets you the vendor's own terms and support.
- **Cost per long episode** (rough):

  | Line | Cost |
  |---|---|
  | Claude | $4–11 |
  | Images | $1–7 |
  | TTS | $0.25–2 |
  | Whisper | cents |
  | Render | <$1 |
  | **Total** | **≈ $6–20** |

  At 12 episodes a month that's ≈ $80–250, plus ~$20–40 fixed AWS and $0 or $100 for Remotion. That's about the same as the self-hosted GPU routes, because Claude dominates either way. **The SaaS case is speed of delivery and lower risk, not cost.**
- **Rules that change or need updating:**
  - The positive-only prompt rule and lint in `visual_rules.py` were built for klein, which has no negative prompt. Keep it per model in config rather than global until a frontier model is tested against it.
  - The `visual_rules.yaml` phrases need re-testing per model.
  - API models give weaker seed control, so reproducibility means keeping every attempt and its parameters (already done), not identical pixels.
  - Record each API's terms in `docs/licenses.md`: commercial use, output ownership, training on your inputs, and watermarks. Google adds SynthID, which is fine because the synthetic-content disclosure is already YES.
  - Cast reference images and scripts leave AWS. Decide if that's acceptable; nothing personal is involved.
  - **Unchanged:** every generated image is still inspected by Claude at full size + crops, bound to SHA-1, whatever model made it.

## 4. Proposed decision path

| Step | What | Effort / cost | Decides |
|---|---|---|---|
| 1 | **TTS bake-off:** add `sarvam`, `elevenlabs` and `gemini_tts` backends to `pipeline/tts_backends.py`. Run the 4 pilot scenes through the segments pipeline with Whisper scoring. Blind listening against Maya2 Vasant / Veena varun. | ~1 day, <$5 | Hosted TTS or a GPU for TTS |
| 2 | **Image bake-off round:** add API backends to `pipeline/bakeoff.py` (Nano Banana Pro, Nano Banana 2.1, GPT-Image, FLUX.2 pro via BFL, Seedream 4.5). Same 12 specs × 3 seeds, plus cast-reference shots of रमेश and सुनीता. Claude inspection + your blind rating at `/bakeoff`. | ~1–2 days, ~$15–30 | Hosted images or a GPU for images |
| 3 | **Hosted Whisper parity:** re-run the §7.4a word-timing measurement on v3. | hours, cents | Whisper host |
| 4 | Pick the architecture: **no-GPU** if steps 1–2 favour the APIs; otherwise AWS + Modal for the stage(s) that stay self-hosted. | — | Final design |
| 5 | Build in this order: GitHub repo + S3 storage layer → Remotion Lambda → API backends → control room with Cognito approvals and the MCP server for interactive Claude → Step Functions + Managed Agents for unattended runs. Take ChatGPT's approval safeguards and the other Claude session's negative tests into the acceptance criteria. | weeks | — |

**Decisions needed from you before step 1:**
- API keys for the candidates: Sarvam, ElevenLabs, Google AI (Gemini), OpenAI, BFL, or fal for all the image models.
- AgriGate's total headcount and revenue, including affiliates. This decides the Remotion licence and FLUX.3 Klein eligibility.
- Whether scripts and cast references may be sent to Google, OpenAI or other model vendors.

## 5. Sources (checked 2026-11-22; most prices from secondary pages, confirm on vendor pages before budgeting)

- Remotion licence and pricing: [remotion.dev/docs/license/pricing](https://www.remotion.dev/docs/license/pricing), [licence FAQ](https://www.remotion.dev/docs/license/faq)
- FLUX.3 Image Klein licence: [bfl.ai model page](https://bfl.ai/models/flux-3-image-klein), [VentureBeat](https://venturebeat.com/technology/black-forest-labs-opens-flux-3-image-klein-weights-with-free-commercial-use-limited-to-smaller-businesses), [Magica](https://magica.com/news/black-forest-labs-flux-3-image-klein-open-weights)
- BFL API pricing: [docs.bfl.ai pricing](https://docs.bfl.ai/quick_start/pricing), [OpenRouter FLUX.2 pro](https://openrouter.ai/black-forest-labs/flux.2-pro/api)
- Nano Banana pricing and references: [Google: Nano Banana Pro](https://blog.google/technology/ai/nano-banana-pro), [pricing summary](https://www.activepieces.com/blog/nano-banana-api-pricing-cost-per-image-in-2026.md), [Nano Banana 2.1 pricing](https://tech-insider.org/nano-banana-2-1-launches-halves-image-price-2026/), [developer reports on multi-reference regressions](https://discuss.ai.google.dev/t/gemini-3-0-pro-image-preview-inconsistent-performance-with-multiple-reference-images-since-3-1-launch/128648)
- OpenAI image pricing: [developers.openai.com pricing](https://developers.openai.com/api/docs/pricing)
- fal.ai prices: [fal.ai/pricing](https://fal.ai/pricing), [summary Nov 2026](https://markaicode.com/pricing/fal-ai-pricing/)
- Hindi TTS: [Sarvam TTS](https://www.sarvam.ai/apis/text-to-speech), [Indic TTS benchmark (vendor-adjacent)](https://caller.digital/blog/indic-tts-benchmark-bulbul-elevenlabs-sarvam-google-ai4bharat-2026), [TTS API comparison](https://www.forasoft.com/blog/article/synthetic-voice-library-apps)
- Hindi STT: [Sarvam STT docs](https://docs.sarvam.ai/api-reference-docs/speech-to-text/transcribe), [ElevenLabs Scribe Hindi](https://elevenlabs.io/speech-to-text/hindi), [Soniox Hindi](https://soniox.com/speech-to-text/hindi), [Deepgram Hindi](https://deepgram.com/product/speech-to-text/hindi)
- Claude Managed Agents: [Anthropic launch post](https://claude.com/it/blog/claude-managed-agents), [pricing write-up](https://www.mindstudio.ai/blog/managed-agents-pricing-token-costs)
- Modal GPU pricing: [modal.com/pricing](https://modal.com/pricing)
