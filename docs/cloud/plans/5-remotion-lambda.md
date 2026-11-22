# Plan 5: Remotion Lambda rendering

**Goal:** draft (540p), final (1080p) and thumbnail renders run on Remotion Lambda reading assets from S3, with output identical to local renders.

**Licence first:** Remotion is free for organisations of ≤ 3 people (whole AgriGate incl. affiliates). Otherwise the Automators plan ($0.01 per render, $100/month minimum). Settle in plan 0 before any production render. Stay on pinned 4.0.545; `@remotion/lambda` must match that exact version.

## Steps

1. `cd remotion && npm i @remotion/lambda@4.0.545 --save-exact`. Record in `docs/licenses.md`.
2. Deploy once: `npx remotion lambda functions deploy` (memory ~3 GB, timeout 240 s, region ap-south-1 if supported; check `npx remotion lambda regions`) and `npx remotion lambda sites create src/index.ts --site-name agrigate-<version>`. Fonts (Devanagari variable font) must be in the bundle, not loaded from the Mac.
3. **Assets by URL.** Today `render.sync_assets()` hard-links files into `remotion/public` and props use `staticFile()` paths. For Lambda, props must carry HTTPS URLs: presigned S3 URLs (valid a few hours) for audio, images, B-roll. Add a `asset_base` / per-asset URL mode in `sync_assets` and make the compositions accept either a `staticFile` path or a full URL (one helper in `remotion/src/`). Keep `types.ts` ↔ `schema.py` in step.
4. `pipeline/render.py --lambda` calls `renderMediaOnLambda` via a small Node script (`remotion/scripts/render-lambda.mjs`) taking props JSON, returning the S3 output key and cost; download to `render/draft.mp4` / `video.mp4` locally until plan 6. Thumbnail via `renderStillOnLambda`.
5. Concurrency: check the account's Lambda concurrency quota (new accounts can be 10); request an increase if renders throttle.

## Acceptance

- Re-render 3 past episodes on Lambda and locally: same duration and frame count (`pipeline.common.episode_frames`), SSIM ≥ 0.99 on sampled frames, Devanagari conjuncts and matras identical on a contact sheet (`pipeline.review`), loudness within 0.5 LU.
- Record time and cost per render in `docs/timings.md`.
