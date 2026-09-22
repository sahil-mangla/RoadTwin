---
phase: 01-schema-core-data-contracts
plan: 03
subsystem: frontend
tags: [react, vite, typescript, fastapi, walking-skeleton]

requires:
  - phase: 01-schema-core-data-contracts (Plan 02)
    provides: "Running FastAPI app with POST/GET /api/skeleton/reports, gated on settings.skeleton_routes_enabled, CORS pre-configured for the Vite dev origins"
provides:
  - "frontend/ scaffold: hand-pinned React 19.3.0 + Vite 8.3.0 + TypeScript 7.0.2 app, closed seven-package dependency allowlist, strict TypeScript, /api dev proxy to localhost:8000"
  - "frontend/src/types.ts: Report/ReportCreatePayload/ReportStatus TypeScript contracts mirroring backend/schemas/report.py field-for-field"
  - "frontend/src/api/client.ts: typed listReports/createReport fetch wrapper that surfaces HTTP status + FastAPI detail body as a readable Error"
  - "frontend/src/pages/SkeletonPage.tsx: report creation form + live list, rendering unverified status and GPS accuracy from real server data"
  - "README.md: four-command full-stack local run sequence, test command, Phase 1 scope note"
affects: ["01-04", "01-05"]

tech-stack:
  added:
    - "React 19.3.0, react-dom 19.3.0 (pinned)"
    - "Vite 8.3.0 (pinned ^8.3.0)"
    - "@vitejs/plugin-react 6.1.1, typescript 7.0.2, @types/react(-dom) 19.3.0 (all resolved via npm view, not guessed)"
  patterns:
    - "Vite dev proxy (/api -> http://localhost:8000) so the frontend uses same-origin relative fetch URLs instead of hardcoding a backend host"
    - "tsconfig.node.json as a composite TypeScript project reference for vite.config.ts, with outDir/tsBuildInfoFile routed into node_modules/.tmp so build artifacts never land in the source tree"
    - "Form uses HTML min/max/step as a UX hint only (noValidate on <form>) so out-of-range values reach the server and the authoritative 422 response is what surfaces to the user -- never silently blocked client-side"

key-files:
  created:
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/.gitignore
    - frontend/tsconfig.json
    - frontend/tsconfig.node.json
    - frontend/vite.config.ts
    - frontend/index.html
    - frontend/src/main.tsx
    - frontend/src/styles.css
    - frontend/src/types.ts
    - frontend/src/api/client.ts
    - frontend/src/pages/SkeletonPage.tsx
    - README.md
  modified:
    - frontend/src/App.tsx

key-decisions:
  - "Hand-authored frontend/package.json instead of a scaffolder (npm create vite@latest) per threat T-01-SC; resolved the four unpinned devDependency versions via `npm view <pkg> version` rather than guessing"
  - "Added noValidate to the report form so the HTML min/max attributes never block submission client-side -- the server (ReportCreate) stays the sole authority on validity, matching the threat model's stated intent for T-01-01"

requirements-completed: [SCHM-03, SCHM-04]

coverage:
  - id: D1
    description: "npm --prefix frontend run dev serves the skeleton page at http://localhost:5173, listing reports fetched from the backend"
    requirement: SCHM-03
    verification:
      - kind: automated_ui
        ref: "playwright:skeleton-page.png (real Chromium screenshot against the running Vite dev server + uvicorn backend)"
        status: pass
      - kind: integration
        ref: "curl through the Vite proxy at http://localhost:5173/api/skeleton/reports"
        status: pass
    human_judgment: false
  - id: D2
    description: "Submitting the form creates a report and the new row appears in the list without a page reload"
    requirement: SCHM-03
    verification:
      - kind: automated_ui
        ref: "playwright:skeleton-page.png -- POST via the real form, row rendered with lat/lon/accuracy/description, no refetch (state prepend)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Each listed report shows its unverified status badge and GPS accuracy in metres, rendered from raw server data"
    requirement: SCHM-04
    verification:
      - kind: automated_ui
        ref: "playwright:skeleton-page.png shows badge text 'unverified' and accuracy '8 m' sourced from report.status / report.gps_accuracy_meters"
        status: pass
    human_judgment: false
  - id: D4
    description: "Submitting latitude 91 surfaces the backend's 422 validation error in the UI instead of silently failing"
    requirement: SCHM-04
    verification:
      - kind: automated_ui
        ref: "playwright:skeleton-page-error.png -- error banner reads 'Request failed with status 422 Unprocessable Content: ...Input should be less than or equal to 90...'; row count unchanged"
        status: pass
    human_judgment: false
  - id: D5
    description: "README.md documents a four-command sequence that boots the full stack from a clean checkout"
    requirement: SCHM-04
    verification:
      - kind: other
        ref: "node -e literal-fragment check against README.md (docker compose up -d postgres / alembic upgrade head / uvicorn backend.main:app / npm --prefix frontend run dev / http://localhost:5173)"
        status: pass
    human_judgment: false

duration: 12min
completed: 2026-09-22
status: complete
---

# Phase 1 Plan 3: Frontend Walking Skeleton & Full-Stack Run Summary

**Hand-pinned React 19 + Vite 8 + TypeScript app whose single page creates and lists reports through the Plan 02 FastAPI skeleton API, closing the Walking Skeleton loop with a real Chromium-verified browser round trip.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-22T13:58:48Z
- **Completed:** 2026-09-22T14:10:00Z
- **Tasks:** 2/2 completed
- **Files modified:** 13 created, 1 modified

## Accomplishments

- Hand-authored `frontend/package.json` with a closed, reviewed seven-package dependency set (no scaffolder run, per threat T-01-SC); `react`/`react-dom` pinned to `19.3.0`, `vite` pinned `^8.3.0` per CLAUDE.md, and the remaining four devDependencies resolved to their concrete current versions via `npm view` (`@vitejs/plugin-react@6.1.1`, `typescript@7.0.2`, `@types/react@19.3.0`, `@types/react-dom@19.3.0`) rather than left floating
- Strict TypeScript project (`"strict": true`, ES2022, bundler resolution) builds and typechecks cleanly, with `vite.config.ts` covered by a separate composite `tsconfig.node.json` project reference; a `server.proxy` maps `/api` to `http://localhost:8000` so the browser uses same-origin relative fetch URLs
- `frontend/src/types.ts` mirrors `backend/schemas/report.py` field-for-field, including the exact four D-06 `ReportStatus` literals in locked order (`unverified`, `corroborated`, `evidence_confirmed`, `rejected`)
- `frontend/src/api/client.ts`'s `listReports`/`createReport` both inspect `response.ok` and throw a readable `Error` combining the HTTP status and the FastAPI `detail` body on failure
- `SkeletonPage` renders a pre-filled (Bengaluru coords) create form and a live report table; on submit it prepends the server's returned report to local state (proving the round trip, not just a refetch) and renders the server's raw `status` string as the badge and `gps_accuracy_meters` with an explicit "no accuracy reported" fallback for `null`
- `README.md` documents the exact four-step full-stack local run sequence plus a test command and a Phase 1 scope pointer
- **Verified end-to-end with a real headless Chromium browser (Playwright)** against the actual running `uvicorn` + `vite dev` processes -- not just curl or the ASGI test client: a valid submit renders the new row with `unverified` status and `8 m` accuracy with no page reload (screenshot captured); submitting latitude `91` surfaces `Request failed with status 422 Unprocessable Content: ...Input should be less than or equal to 90...` in the error banner and adds no row (screenshot captured)

## Task Commits

1. **Task 1: Scaffold the Vite + React 19 + TypeScript frontend with a dev proxy to the API** - `d972d97` (feat)
2. **Task 2: Build the skeleton page that creates and lists reports, and document the full-stack run** - `546be3f` (feat)

## Files Created/Modified

- `frontend/package.json` - hand-pinned 7-package dependency allowlist, `dev`/`build`/`preview`/`typecheck` scripts
- `frontend/package-lock.json` - committed lockfile for reproducible installs
- `frontend/.gitignore` - `node_modules/`, `dist/`, `.vite/`
- `frontend/tsconfig.json` - strict TS project for `src`, references `tsconfig.node.json`, `types: ["vite/client"]` for CSS side-effect imports
- `frontend/tsconfig.node.json` - composite project covering `vite.config.ts`, build output routed to `node_modules/.tmp`
- `frontend/vite.config.ts` - React plugin, port 5173, `/api` proxy to `http://localhost:8000`
- `frontend/index.html` - root document, module script importing `/src/main.tsx`
- `frontend/src/main.tsx` - `createRoot` + `StrictMode` bootstrap, imports `styles.css`
- `frontend/src/App.tsx` - heading/scope note, renders `SkeletonPage`
- `frontend/src/styles.css` - minimal system-font layout, `.status-badge`, `.error-banner`
- `frontend/src/types.ts` - `Report`, `ReportCreatePayload`, `ReportStatus` contracts
- `frontend/src/api/client.ts` - `listReports`/`createReport` typed fetch wrapper
- `frontend/src/pages/SkeletonPage.tsx` - create form + live report list
- `README.md` - project overview, prerequisites, four-step run sequence, test command, scope note

## Decisions Made

- Resolved `@vitejs/plugin-react`, `typescript`, `@types/react`, `@types/react-dom` to their concrete current versions via `npm view <pkg> version` at execution time (6.1.1 / 7.0.2 / 19.3.0 / 19.3.0 respectively) rather than guessing or leaving `latest` -- per the plan's explicit instruction and threat T-01-SC.
- Added `noValidate` to the report `<form>` so the HTML `min`/`max` attributes on the coordinate inputs remain a UX convenience only, never a blocker -- keeping the server's `ReportCreate` Pydantic validation as the sole authority, which is what the plan's own threat model (T-01-01) and human-check step require.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `tsc -b` failed: referenced project must be `composite: true` and may not disable emit**
- **Found during:** Task 1, first `npm run build`
- **Issue:** `frontend/tsconfig.node.json` as originally written per the plan's literal spec (`noEmit: true`, no `composite`) is invalid as a TypeScript project reference target for `tsc -b` (TS6306/TS6310).
- **Fix:** Added `"composite": true` to `tsconfig.node.json`, removed `noEmit`, and routed its emitted output (`outDir`, `tsBuildInfoFile`) into `node_modules/.tmp/` so no stray `.js`/`.d.ts`/`.tsbuildinfo` files land in the source tree.
- **Files modified:** `frontend/tsconfig.node.json`
- **Verification:** `npm --prefix frontend run build` exits 0; `git status` after build shows zero stray generated files outside `node_modules/`.
- **Committed in:** `d972d97` (Task 1 commit)

**2. [Rule 1 - Bug] `tsc` could not resolve the side-effect `import "./styles.css"` in `main.tsx`**
- **Found during:** Task 1, first `npm run build`
- **Issue:** `TS2882: Cannot find module or type declarations for side-effect import of './styles.css'` -- the root `tsconfig.json` had no `vite/client` ambient type declarations, which is what declares CSS-as-side-effect imports as valid under Vite's bundler resolution.
- **Fix:** Added `"types": ["vite/client"]` to `frontend/tsconfig.json`'s `compilerOptions`.
- **Files modified:** `frontend/tsconfig.json`
- **Verification:** `npm --prefix frontend run build` and `npm --prefix frontend run typecheck` both exit 0.
- **Committed in:** `d972d97` (Task 1 commit)

**3. [Rule 1 - Bug] Browser-native HTML5 constraint validation silently blocked the 422 error path the plan's human-check requires**
- **Found during:** Task 2, real-browser verification of the "submit latitude 91" scenario via Playwright
- **Issue:** The `min={-90} max={90}` attributes on the latitude `<input>` (required by the plan's own task instructions) cause Chromium to block form submission entirely via native constraint validation, showing its own browser tooltip ("Value must be less than or equal to 90") -- the `onSubmit` handler, and therefore `createReport`, never runs. This means the backend's 422 rejection could never reach the UI as written, directly contradicting the plan's own threat-model mitigation for T-01-01 ("HTML min/max attributes are a convenience only; the authoritative check stays server-side ... the human-check step explicitly exercises latitude 91 to prove the backend rejection surfaces in the UI") and the Task 2 acceptance criterion itself.
- **Fix:** Added `noValidate` to the `<form>` element. The `min`/`max`/`step` attributes remain in place as a UX hint (spinner behavior, semantic markup) but no longer block submission; the server's `ReportCreate` validation is now the sole authority, exactly as the threat model specifies.
- **Files modified:** `frontend/src/pages/SkeletonPage.tsx`
- **Verification:** Re-ran the Playwright script against the running dev server -- error banner now reads `Request failed with status 422 Unprocessable Content: [{"type":"less_than_equal",...,"msg":"Input should be less than or equal to 90",...}]`, row count unchanged at 1 (screenshot `skeleton-page-error.png` captured before and after the fix, confirming the before-state showed only the browser's native tooltip and no banner).
- **Committed in:** `546be3f` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (2 Rule 3 blocking build-config bugs, 1 Rule 1 correctness bug affecting the plan's own acceptance criteria)
**Impact on plan:** All three were necessary for the plan's literal acceptance criteria and human-check to be satisfiable at all -- none expand scope beyond what Task 1/2 already specified. The third fix in particular was caught only because the human-check was actually automated with a real browser rather than assumed to pass.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required. The verification session started `uvicorn backend.main:app --port 8000` and `npm --prefix frontend run dev` in the background, exercised both the valid-submit and invalid-submit (latitude 91) flows through a real Chromium browser via Playwright, then stopped both processes and deleted the one test report row it created (`DELETE FROM report WHERE description = 'Pothole near MG Road'`) so the dev database is clean. Docker Desktop must remain running for `docker compose up -d postgres`, same as prior plans.

## Next Phase Readiness

Plan 04 (remaining six entities) and Plan 05 can proceed immediately -- this plan touched no backend file and introduced no schema changes, so there is no collision risk. The Walking Skeleton is now closed end-to-end: a human (or an automated browser) can open `http://localhost:5173`, submit a report, and see it persisted in Postgres with its `unverified` status and GPS accuracy radius rendered back, with the backend's validation surfacing readably on bad input. No blockers.

---
*Phase: 01-schema-core-data-contracts*
*Completed: 2026-09-22*

## Self-Check: PASSED

All 14 created/modified files confirmed present on disk (`frontend/package.json`, `frontend/package-lock.json`, `frontend/.gitignore`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/styles.css`, `frontend/src/types.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/SkeletonPage.tsx`, `frontend/src/App.tsx`, `README.md`). Both task commits (`d972d97`, `546be3f`) confirmed present in `git log --oneline --all`. `npm --prefix frontend run build` and `run typecheck` both exit 0. Full backend test suite: 14/14 passing (unaffected, as expected). Real-browser (Playwright/Chromium) verification confirmed both the valid-submit and invalid-submit (422) flows render exactly as the plan's human-check specifies. No missing items.
