/**
 * This file is the composition root: it reads the inputs, wires the domain and
 * service layers together, and publishes the results. All logic lives in the
 * modules it calls, and the process-level bootstrap lives in `index.ts`.
 *
 * Step 1 - resolve which thread (issue or pull request) triggered the workflow.
 * Step 2 - make sure the session-log comment exists on that thread.
 *
 */

import * as github from "@actions/github";

import { readInputs } from "./config/inputs";
import { exportCommentId, exportThread } from "./config/outputs";
import { buildMarker } from "./domain/marker";
import { resolveThread } from "./domain/thread-resolver";
import { ensureSessionLogComment } from "./services/session-log.service";

/**
 * Entry point.
 *
 * @throws Error when the triggering event is unsupported, when a required
 *   input is missing, or when the GitHub API call fails.
 * @returns None.
 */
export async function run(): Promise<void> {
  // `github.context.issue` reads GITHUB_REPOSITORY, which the runner always
  // sets, and throws a descriptive error when it is absent.
  const thread = resolveThread(github.context);
  exportThread(thread);

  const { token } = readInputs();
  const client = github.getOctokit(token);
  const marker = buildMarker(thread);

  const commentId = await ensureSessionLogComment(client, thread, marker);
  exportCommentId(commentId);
}
