# Plan 0: Decisions and housekeeping

**Goal:** collect the answers and accounts every other plan needs, and fix stale licence entries.

## Decisions needed from the user

| Decision | Why it matters | Blocks |
|---|---|---|
| API keys to test: Sarvam, ElevenLabs, Google AI (Gemini), OpenAI, Black Forest Labs or fal.ai, Groq (Whisper) | No key, no bake-off | 1, 2, 3 |
| May scripts, narration text and cast reference images be sent to these vendors? Check each vendor's data-retention / training terms (API data is usually not trained on; confirm) | Cast faces are synthetic, but scripts are AgriGate content | 1, 2, 3 |
| AgriGate's total headcount and annual revenue, **including affiliates** | Remotion free only for ≤ 3 people, else Automators $0.01/render, $100/month minimum. FLUX.3 Klein free only below US$5M revenue | 2, 5 |
| AWS account: new dedicated account, or a separate stack in the existing AgriGate account? Region ap-south-1? | Isolation of IAM, budgets | 4, 5, 6 |
| Claude billing: Anthropic API (Managed Agents available) or Bedrock (single AWS bill; no Managed Agents) | Decides how agent steps run | 6 |
| Approver of record: the operator, or a separate reviewer (agronomist)? | Cognito groups, notifications | 6 |
| Data residency: may non-personal media leave India (US/EU APIs)? | Most image/TTS APIs are not in India | 1, 2, 3 |

## Housekeeping (do on approval, ~15 min)

1. `docs/licenses.md:37` lists `flux-3-image-klein` as "no" (non-commercial). Correct it to the revenue-capped community licence (free below US$5M revenue incl. affiliates; above that, a BFL licence), matching line 54.
2. `docs/ARCHITECTURE.md` decision D5: same correction.
3. `docs/cloud/proposal-claude.md`: already corrected for Remotion; re-check nothing else says "buy the company licence".
4. Add a "Hosted APIs" section to `docs/licenses.md` with columns: vendor, model, commercial use, data retention, training on inputs, region, date checked. Fill it as plans 1–3 add vendors.

## Done when

- Every row above has an answer recorded in this file (append an "Answers" section with the date).
- Keys are stored outside the repo: `.env` (gitignored) for local bake-offs; Secrets Manager once plan 4 exists. Verify `.env` is in `.gitignore` before writing it.
