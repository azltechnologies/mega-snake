/**
 * Process-level entry point of the action.
 *
 * Kept apart from `main.ts` so the composition root is an ordinary async
 * function a test can await, instead of something that runs on import.
 */

import * as core from "@actions/core";

import { run } from "./main";

run().catch((error: unknown) => {
  // `setFailed` prints `::error::<message>` and sets the exit code to 1,
  // which is what `echo "::error::..." && exit 1` did in the shell version.
  core.setFailed(error instanceof Error ? error.message : String(error));
});
