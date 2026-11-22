# Cloud move: execution plans

Written 2026-11-22, after comparing four architecture answers (`../comparison.md`). The user prefers frontier model APIs and SaaS over self-hosted GPU models. Each plan stands alone: a later session can open one and execute it without re-reading the whole discussion.

| # | Plan | Depends on | Effort | Spend | Unblocks |
|---|---|---|---|---|---|
| 0 | [Decisions and housekeeping](0-decisions-and-housekeeping.md) | user answers | 1 h | $0 | everything |
| 1 | [TTS API bake-off](1-tts-api-bakeoff.md) | 0 (keys) | ~1 day | < $5 | narration choice |
| 2 | [Image API bake-off](2-image-api-bakeoff.md) | 0 (keys) | 1–2 days | $15–30 | image choice |
| 3 | [Hosted Whisper parity](3-hosted-whisper-parity.md) | 0 (key) | ½ day | < $2 | no-GPU narration |
| 4 | [Cloud storage foundation](4-cloud-storage-foundation.md) | 0 (AWS account) | 3–5 days | < $5/mo | 5, 6 |
| 5 | [Remotion Lambda rendering](5-remotion-lambda.md) | 4 | 2–3 days | ~$1 test | 6 |
| 6 | [Orchestration, checkpoints, control room](6-orchestration-and-control-room.md) | 1–5 | 2–3 weeks | ~$15/mo fixed | cloud-only episodes |

**Order.** Plans 1, 2 and 3 are independent and cheap; run them first, because their results decide whether any GPU vendor is needed at all. Plan 4 can run in parallel with them (it changes no generation). Plan 5 needs 4. Plan 6 comes last and assumes the winners of 1–3.

**Decision gate after 1–3.**
- If hosted TTS **and** hosted images match or beat the Mac models: no-GPU design (AWS + APIs + Remotion Lambda). Skip all MLX→CUDA porting.
- If one loses: that stage alone goes to Modal (GPU per second); see `../proposal-claude.md` §G for the porting notes.
- Record the decision in `docs/ARCHITECTURE.md` (new decision entry) and in `config.yaml` backends.

**Rules that hold in every plan** (from `CLAUDE.md`): the three human checkpoints; every image inspected by Claude at full size and with crops; no `[VERIFY` past the script stage; no voice cloning of real people; no non-commercial models; every new dependency or API recorded in `docs/licenses.md` with its terms; Mac backends stay selectable in `config.yaml` until a cloud replacement passes its acceptance test.
