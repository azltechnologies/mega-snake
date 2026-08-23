# `task` action (TypeScript)

Same behaviour as the composite version in `../task`, written as a **JavaScript
action** (`runs.using: node24`) with a TypeScript source.

## Why not a composite action in TypeScript?

`runs.using: composite` only knows how to run *steps*: `run:` (a shell) and
`uses:` (other actions). It has no TypeScript runtime. The TypeScript path is a
different action type: `runs.using: node24`, whose `main:` points at a single
bundled JavaScript file. GitHub does not compile it for you, so the bundle is
committed.

## Build

```bash
cd .github/actions/task
npm ci
npm run build        # tsc --noEmit + vitest run --coverage + ncc bundle -> dist/index.js
git add dist         # dist/ MUST be committed: the runner executes it as-is
```

## Exported variables

| Variable      | Value                                                     |
| ------------- | --------------------------------------------------------- |
| `THREAD_ID`   | Issue or pull request number that triggered the workflow  |
| `THREAD_TYPE` | `issue` or `pull_request`                                 |
| `COMMENT_ID`  | Id of the session-log comment (found or freshly created)  |

## Inputs

| Input   | Default               | Notes                                        |
| ------- | --------------------- | -------------------------------------------- |
| `token` | `${{ github.token }}` | Used to read and create issue comments.      |

The repository is **not** an input: it is read from `GITHUB_REPOSITORY`, which
the runner sets on every job. Exposing it in `with:` invited a caller to point
the action at an unrelated repository by accident, and forced a `split("/")`
whose failure only surfaced later as an opaque API error.

## Source layout

The split is by *purity*, not by noun - which is what keeps the layers testable:

| Directory   | Contents                                        | Rule                                          |
| ----------- | ----------------------------------------------- | --------------------------------------------- |
| `models/`   | `ThreadContext`, `Repository`, `ActionInputs`   | Data shapes only; **no `@actions/*` imports**  |
| `domain/`   | `resolveThread`, `buildMarker`                  | Pure functions: data in, data out; no I/O      |
| `services/` | `comments.service`, `session-log.service`       | GitHub API calls; the client is **injected**   |
| `config/`   | `inputs`, `outputs`                             | The only callers of `getInput`/`exportVariable`|
| `main.ts`   | `run()`                                         | Composition root: wires the above, no logic    |
| `index.ts`  | bootstrap                                       | Calls `run()` and maps a rejection to `setFailed` |

## Tests

```bash
npm test          # vitest run
npm run test:watch
npm run coverage  # v8 coverage, fails under 95%
```

Tests live in `src/tests/`, mirroring the source tree. `npm run build` runs
them, so a broken suite cannot produce a `dist/` bundle.
