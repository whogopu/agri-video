# Plan 4: Cloud storage foundation

**Goal:** episodes live in S3 instead of only on the Mac, with `episode.json` still the single source of truth and safe against parallel writers. Nothing about generation changes yet; the Mac keeps working against a local mirror.

## Steps

1. **Infra (AWS CDK, TypeScript, ap-south-1)** in a new `infra/` folder:
   - S3 bucket `agrigate-video-<env>`: versioning on, SSE (KMS or S3-managed), Block Public Access, lifecycle (unpicked takes and image attempts → Standard-IA 30 d → Glacier IR 90 d; `episode.json` versions kept).
   - DynamoDB on-demand: `episodes` (pk `episode_id`: status, format, episode.json VersionId/ETag, cost totals), `jobs` (pk `episode_id`, sk `job_id`), `costs` (pk `episode_id`, sk `stage#ts`).
   - Secrets Manager entries for the API keys from plan 0.
   - AWS Budgets alerts at 80/100/120 % of a monthly figure.
   - GitHub Actions OIDC role for deploys (no stored AWS keys).
2. **Layout** (same file names as today, so a pull reproduces the local folder):
   ```
   episodes/{id}/episode.json, brief.md, script.md, log.md, sources/, audio/, images/, render/, review/
   episodes/{id}/results/{stage}/{item}/{attempt}-{hash}.json   ← immutable worker outputs (plan 6)
   shared/cast/, shared/brand/, shared/rules/visual_rules.yaml, shared/rules/pronunciation.yaml
   ```
3. **Sync CLI** `pipeline/sync.py`: `push <episode>` / `pull <episode>` / `status`. Use content hashes to skip unchanged files. `episode.json` is pushed with an S3 conditional write (`If-Match` on the last-seen ETag); on 412, stop and tell the user (someone else changed it).
4. **Single-writer merge (library first).** `pipeline/merge.py`: `apply_result(episode, result) -> episode` using the pydantic models, idempotent (keyed by item + attempt hash). Used later by the merge Lambda (plan 6); usable locally now. Unit tests: 40 parallel fake results applied in random order give the same `episode.json`.
5. **Storage abstraction.** `pipeline.common.load_episode/save_episode` stay local-file based; the sync layer mirrors. Don't rewrite stages to talk to S3 yet.

## Acceptance

- Round-trip every existing episode: push then pull into an empty folder; every file's SHA-256 identical; `episode.json` validates unchanged.
- Concurrent-write test: two `push` of different `episode.json` edits; the second gets 412.
- Monthly cost at today's size: a few dollars.

## Notes

- Ask the user before creating AWS resources (outward-facing, costs money). Use the AWS MCP tools, not the CLI via Bash.
- `remotion/public` hard-link trick (`pipeline/render.py: sync_assets`) is unaffected.
