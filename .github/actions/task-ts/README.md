# `task` action (TypeScript)

Same behaviour as the composite version in `../task`, written as a **JavaScript
action** (`runs.using: node20`) with a TypeScript source.

## Why not a composite action in TypeScript?

`runs.using: composite` only knows how to run *steps*: `run:` (a shell) and
`uses:` (other actions). It has no TypeScript runtime. The TypeScript path is a
different action type: `runs.using: node20`, whose `main:` points at a single
bundled JavaScript file. GitHub does not compile it for you, so the bundle is
committed.

## Build

```bash
cd .github/actions/task-ts
npm ci
npm run build        # tsc --noEmit + ncc bundle -> dist/index.js
git add dist         # dist/ MUST be committed: the runner executes it as-is
```

## Exported variables

| Variable      | Value                                                     |
| ------------- | --------------------------------------------------------- |
| `THREAD_ID`   | Issue or pull request number that triggered the workflow  |
| `THREAD_TYPE` | `issue` or `pull_request`                                 |
| `COMMENT_ID`  | Id of the session-log comment (found or freshly created)  |
