# Part C review fixes and browser evidence

Reviewed baselines: `ea249be` and `a3ae3ae`. Verification date: 2026-10-12 (Asia/Taipei).

All screenshots and browser records use a separate local SQLite database and the participant ID `llm_synthetic_part_c_e2e`. The server runs with `PREFERENCE_LAB_DECISION_SOURCE=synthetic_mock`, so DecisionRecord provenance, SQLite and downloaded ZIP all identify them as synthetic. They are automated test evidence, not human research observations. Databases, browser profiles and session tokens stay in ignored `runs/part-c/`.

## Corrections

| Finding | Implemented behavior |
| --- | --- |
| BRET pilot submission | Open the decision before enabling submission; use the returned trial version. |
| 45-second flow | Open the primary decision once at 45 seconds of active play. Persist the post-decision starting time; after another 45 seconds, end play and offer solution followup or next trial. Server rejects a second primary decision. |
| Cross-trial contamination | Mount environment components by trial ID. Draft keys and clocks are scoped to that ID. New trials start with blank acceptability, choice and reason. |
| Idempotent retry | Persist the first complete decision payload and key before sending. Transport failures retain it; refresh replays identical JSON. A definitive version rejection permits a new confirmation without altering an uncertain request. |
| Refresh and blur | Save local time every tick, checkpoint to the server every five seconds, preserve form drafts and deliberation start time, and call pause on blur/hidden. Resume is explicit. Transient rejoin failures preserve the saved code and drafts. |
| Display order | Sort Puzzle actions and BRET options using saved `display_order`; check it again after reload. |
| Unasked preference data | Omit `preferred_action_ids`; backend stores its default null. |

Also corrected Chinese labels and clue text, the authoritative `revealed_hint` field, BRET tutorial data bindings, the modal skip button and keyboard focus loop, neutral outcome/pilot copy, `PL-XXXX` entry instructions, and `?view=operator`. Puzzle controls and the default decision modal fit at 1280×720. BRET uses ordinary vertical scrolling; the pilot screenshot shows all choices and the submit control.

## Followup review corrections at a3ae3ae

- Removed arbitrary fresh-version substitution. A queued command can advance its captured version only through successful predecessor requests that were already pending in this same client when it was enqueued. Failed predecessors block dependents. External writes still cause a server version conflict, synchronize the participant view, and ask for reconfirmation; no stale board/check is automatically replayed.
- Puzzle and BRET retain and show the frozen submission on uncertain transport failure. Choice, ratings, reason, override and skip controls are disabled; the explicit button says “重試原提交”. A definitive state-version rejection clears the pending request and permits editing and a new confirmation/key. Other failures retain the request conservatively.
- Decision provenance is controlled only by the trusted server configuration `PREFERENCE_LAB_DECISION_SOURCE` (`human_gui` by default; `synthetic_mock` for isolated tests). Invalid values fail; participant JSON cannot override it. API integration tests verify persisted SQLite and ZIP source values for both configurations.
- The researcher's ZIP control now downloads with the operator authentication header. The browser creates the main session through the researcher form, opens its completed detail, clicks ZIP export, waits for the actual downloaded file, then compares its nonempty decision IDs and sources with SQLite.

## Actual verification

- Backend: **69 passed, 1 warning** (Starlette's httpx deprecation).
- Frontend: `npm run build` passed.
- Frontend: `npm run lint` passed with **18 warnings**, primarily React effect/ref/dependency diagnostics; this is not a warning-free result. Lint is scoped to source, scripts and Vite configuration so installed dependencies are not lint targets.
- Chrome headless at **1280×720**: **110 logged checks passed**, plus strict equality/order assertions. No browser runtime exceptions.
- Every failed assertion throws and exits nonzero. Earlier failures exposed the duplicate StrictMode restore and missing BRET tutorial bindings; those runs were not reported as passes.

The browser session traverses all 12 trials: first Puzzle uses continue and the real 45-second followup timeout; second Puzzle skips via keyboard from the decision modal; third submits hint and then skips; the remaining three submit solution. Definitive version rejection is tested in both decision forms, followed by changing and successfully committing a new choice. BRET also loses an accepted response, locks the form, and retries the exact original payload through its explicit button. Two independent browser windows reproduce caller version 1 versus server version 9 for board and check-answer; a further check interleaves an external write between locally queued commands and asserts rejection. Both BRET tutorials complete, and all four BRET pilot rounds submit and reveal their results. It checks visible timer resets, blank answers, saved display order, draft and active-time reload recovery, actual tab-switch pause, focus wrapping, and a lost response injected after server acceptance. The retry is byte-for-byte identical and produces one decision record and one primary opening.

Run from `frontend/`:

```powershell
npm run build
npm run lint
npm run test:e2e
```

The E2E runner starts isolated API/Vite processes on 18732/18731, creates a new test database, launches a separate Chrome profile and stops its child servers. It requires the existing `backend/.venv` with backend dependencies and Chrome; set `CHROME_PATH` for another executable. The Python path defaults to the Windows venv used here. `APP_URL` and `API_URL` override local test ports; occupied ports fail rather than reuse another service.

Backend command from `backend/`:

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp ../runs/part-c/pytest-final
```

## Screenshots

All captures are viewport images, not long-page screenshots.

- [Participant Puzzle](part-c-evidence/participant-puzzle.png)
- [Decision modal](part-c-evidence/decision-modal.png)
- [Paused state](part-c-evidence/paused.png)
- [BRET demonstration tutorial](part-c-evidence/bret-tutorial.png)
- [BRET comprehension](part-c-evidence/bret-comprehension.png)
- [BRET pilot choices](part-c-evidence/bret-pilot.png)
- [BRET result](part-c-evidence/bret-result.png)
- [Operator](part-c-evidence/operator.png)
- [Operator creation](part-c-evidence/operator-created.png)
- [Operator completed detail](part-c-evidence/operator-detail.png)
- [Puzzle pending original submission](part-c-evidence/puzzle-pending.png)
- [BRET pending original submission](part-c-evidence/bret-pending.png)
- [Machine-readable assertions](part-c-evidence/report.json)

## Remaining limits

Evidence covers local desktop Chrome automation. It does not establish physical-device, mobile, Firefox/Safari, screen-reader, production deployment or human-study acceptance. Keyboard checks cover the modal focus loop and skip action, not a full accessibility audit. Lint warnings remain. Drafts/checkpoints are browser-local and do not provide recovery on another device or after browser storage is cleared.
