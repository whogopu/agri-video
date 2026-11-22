# Plan 6: Orchestration, checkpoints, control room

**Goal:** a whole episode runs from brief to `packaged` with nothing on the Mac. Humans approve the three checkpoints from a phone; no automated part can approve.

**Assumes:** plans 1–3 decided the backends (APIs or Modal), plan 4 storage, plan 5 rendering.

## Components

| Piece | Service | Notes |
|---|---|---|
| Workflow | Step Functions Standard, one execution per episode | Map over sentences and shots (max concurrency ~8); retries with backoff on 429/5xx; content failures never retried blindly |
| Checkpoints | `waitForTaskToken` → Approval Lambda | Token stored in `approvals` table readable only by the Approval role |
| Approval guard | IAM permission boundary on **every** machine role: explicit Deny `states:SendTaskSuccess`, `states:SendTaskFailure`, and writes to `approvals` | Explicit deny beats any allow |
| Who approves | Cognito user in `approver` group, TOTP MFA; machine clients never in it | Approval records episode.json VersionId + SHA-256 of the reviewed MP4; a later change to episode.json invalidates it |
| Workers | Lambda (Python container: normalize, validate, crops, contact sheets, API calls to TTS/image/STT) | Workers never write episode.json; they write `results/…` and emit an event |
| Merge | EventBridge → SQS FIFO (`MessageGroupId = episode_id`) → merge Lambda using `pipeline/merge.py` (plan 4), conditional PUT | One writer per episode; episodes merge in parallel |
| Judgement steps | Claude API: inspection (vision, JSON verdict, cached system prompt + visual_rules), prompt fixing, graphics, review, metadata. **Claude Managed Agents** for script research/writing and applying draft notes (the skills in `.claude/skills/`) | Managed Agents needs the direct Anthropic API, not Bedrock |
| Interactive mode | MCP server over the control-room API (`get_episode`, `run_stage(scene, force)`, `get_media_url`, `record_inspection`), operator scope, **no approve tool** | Lets Claude Code on any device drive the cloud pipeline |
| Control room | React SPA on S3 + CloudFront, API Gateway + Lambda, Cognito Hosted UI | Port of today's `dashboard/` features; polling every 3–5 s; signed CloudFront URLs for media |
| Notifications | SNS email; later WhatsApp (AWS End User Messaging Social) "waiting for approval" with deep link | |

## Workflow shape

1. Script (Managed Agent) → Validate(script, no `[VERIFY`) → **CP1**.
2. Narration: Map over sentences (TTS takes → scoring) → pick → assemble (−14 LUFS) → word timing → Validate(narrated).
3. Visuals: Map over shots: generate → inspect → pass | fix prompt and retry (max 3) | park in NeedsHuman (own token; other shots continue) → Validate(visuals_ready).
4. Graphics → draft render → **CP2**. Reject with notes → ApplyNotes (scene-scoped) → rerun only affected scenes (cache hits elsewhere) → draft → CP2 again.
5. Final render → review → package → **CP3** → (later) YouTube upload as private/scheduled.

Rule changes to `visual_rules.yaml` proposed by the agent arrive as a diff the operator accepts in the control room, never edited silently mid-episode.

## Build order (each shippable)

1. Worker Lambdas + merge + validate, triggered manually from the CLI (no Step Functions yet).
2. Step Functions for narration and visuals only, with a fake checkpoint.
3. Cognito, Approval Lambda, permission boundary, the three real checkpoints.
4. Control room SPA (status, run/stop/retry, review pages per checkpoint, cost per episode/stage from the `costs` table).
5. MCP server for interactive Claude Code.
6. Managed Agents for script and notes; unattended runs.

## Acceptance

- One complete long episode and one Short from brief to `packaged` with zero jobs on the Mac.
- **Negative tests:** the agent role, worker roles and the MCP client each call `SendTaskSuccess` and the approve endpoint and are denied. Editing episode.json after CP2 approval blocks the next step.
- 40 parallel fake results all land in episode.json with no lost update.
- Cost per episode logged per stage and visible in the control room; compare with the Mac baseline (v3: $22.76 Claude).
- `docs/ARCHITECTURE.md` updated for the new runtime.
