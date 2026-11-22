# PLAN-190: fixed sample review

Date: 2026-11-22  
Reviewer: Codex preliminary review; Claude review is still required by PLAN-190.  
Purpose: offline editorial quality check before any live style change. This does not measure engagement.

## Generation proof

- Fixed set: 15 materials, five life-reflection, five fashion, five other; IDs, old captions, source hashes, and titles are in `sample_manifest.json`.
- New drafts, captured transcripts, per-call provider metadata, and source hashes are in `drafts.json`.
- The main PostgreSQL snapshot used a read-only transaction. The orchestrator received copied video files; thumbnails, extracted audio, and pipeline state were redirected to a temporary directory and removed after the run. RPA/browser fallback was blocked. No material caption, setting, schedule, or worker was changed.
- All 15 samples returned a draft with one facade call each; no orchestrator rewrite was needed. Each facade call first received HTTP 400 `chat_completions_disabled` from the primary Xingchi endpoint, then succeeded through the configured 9Router fallback (Gemini 3.8 Flash). This provider issue remains outside this plan's scope.
- Four samples had empty transcripts; several others had only music, short, or visibly noisy transcript text. Those samples were checked against extracted video frames. Missing speech was not treated as proof for details absent from the frames.

## Preliminary scores

Each axis is 0–2: source facts, specific detail, audience voice, natural reply opportunity when suitable, and non-repetitive wording. Passing requires at least 8/10 and source facts 2/2. These are Codex scores to help Claude review, not Claude's sign-off.

| ID | Group | Facts | Specific | Voice | Reply | Variety | Total | Preliminary result / evidence |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 2092 | Life | 2 | 2 | 2 | 2 | 0 | 8 | Pass threshold; on-screen 10-item list supports the cited points. Closing list-question repeats the batch pattern. |
| 2090 | Life | 2 | 2 | 1 | 2 | 0 | 7, fail; list details are visible, but the closing question repeats the same formula. |
| 2091 | Life | 2 | 2 | 1 | 2 | 0 | 7, fail; cited habits are on-screen; repeated list-question formula. |
| 2096 | Life | 2 | 2 | 1 | 2 | 0 | 7, fail; “lúc khó/mất lợi” is on-screen; repeated list-question formula. |
| 2086 | Life | 2 | 2 | 1 | 2 | 0 | 7, fail; cited points are on-screen; repeated list-question formula. |
| 2085 | Fashion | 2 | 2 | 2 | 1 | 1 | 8 | Pass threshold; neckline, puff sleeves, and jeweled brooch are visible; no explicit reply prompt. |
| 2033 | Fashion | 1 | 2 | 1 | 2 | 1 | 7, fail; waist gathering is visible, but “hides the waist” and the assumed body concern are not established by this clip. |
| 2032 | Fashion | 2 | 2 | 2 | 2 | 1 | 9 | Pass; color, dress details, and use case are supported by the clip/text. |
| 2010 | Fashion | 1 | 1 | 1 | 0 | 1 | 4, fail; the fabric claim is uncertain and the “find where to buy” line turns the dialogue into a sales joke without a natural reply. |
| 2026 | Fashion | 1 | 1 | 1 | 1 | 1 | 5, fail; red áo dài and white trim are visible, but silk and the assumed audience concern are not verified. |
| 2071 | Other | 2 | 2 | 2 | 2 | 1 | 9 | Pass; book cover and overlay identify Đại Việt Kỳ Nhân and 51 historical figures. Transcript is unrelated/noisy. |
| 2061 | Other | 2 | 2 | 1 | 1 | 1 | 7, fail; the five family points are visible, but the draft closes as a statement with little reply opportunity. |
| 2084 | Other | 2 | 2 | 2 | 2 | 1 | 9 | Pass; “ở gần, không ở cùng” and boundary with children's private lives are on-screen. |
| 1976 | Other | 2 | 2 | 2 | 2 | 1 | 9 | Pass; fabric stretch, elastic waist, and return-to-form demonstration are visible and in transcript. |
| 2034 | Other | 2 | 2 | 2 | 1 | 2 | 9 | Pass; frog/snake and sea/people contrast matches the on-screen text; reflective close is acceptable without a question. |

## Gate result

- Preliminary threshold pass: **7/15**; by group: life **1/5**, fashion **2/5**, other **4/5**.
- Factual score 2/2: **12/15**; samples 2033, 2010, and 2026 need factual edits or must remain pending.
- Repetition: four of five life-reflection captions use nearly the same “which item in this list is hardest?” closing. Several outputs also make audience assumptions or end without a useful reply opening.
- **AC8 remains FAIL/PENDING. Do not change `ai.caption_style`, restart processes, or roll out this batch.** PLAN-190 requires Claude to review every sample; this preliminary Codex pass cannot replace that review. The failed examples must be improved or remain pending, not replaced with easier samples.

## One prompt revision for failed samples

- Based on the first review, Step 2 prompt now explicitly avoids list-count closing questions, unsupported audience/body assumptions, and inferred fabric/fit/benefit claims. It also tells the model to treat empty/noisy transcript as missing evidence.
- Proof: `pytest tests/test_caption_prompt_contract.py -q` → **12 passed in 1.49s**; `py_compile`, Ruff (`All checks passed!`), and `git diff --check` passed.
- One additional orchestrator run was made for each of the eight samples that failed the first review. The same fixed samples, source videos, and captured transcripts were used; each sample had exactly one extra facade call. Together with the first batch: **23/30** allowed facade calls. Primary endpoint HTTP 400 and successful 9Router fallback are logged in `drafts.json`.

| ID | Revised score | Revised result / evidence |
|---:|---:|---|
| 2090 | 8 | Pass threshold; source-listed emotions, speech, patience, and sincerity; no repeated list-count question. |
| 2091 | 9 | Pass; visible habits retained; statement form avoids another forced question. |
| 2096 | 9 | Pass; hardship and self-interest are visible; avoids asking the reader to choose a list item. |
| 2086 | 9 | Pass; the lines about speaking in anger and speaking unasked are visible; no repeated closing formula. |
| 2033 | 9 | Pass; revised copy sticks to visible color, length, pleating, and brooch; removed body concern/benefit claim. |
| 2010 | 9 | Pass; revised copy uses the visible brown top, drawstring pants, and flower hair clip; ends with a grounded color-preference question. |
| 2026 | 9 | Pass; revised copy uses visible red áo dài, white bow, and flared sleeve; removed inferred audience fear. |
| 2061 | 6 | Fail; the opening still invents that people search elsewhere for feng shui/wealth, and the copy closes without a reply opening. |

Final preliminary total: **14/15** samples at or above 8/10 with facts 2/2. Sample 2061 remains below threshold; therefore **AC8 remains FAIL/PENDING**, and no live style setting or rollout was performed. Claude review and Anti sign-off remain required.
