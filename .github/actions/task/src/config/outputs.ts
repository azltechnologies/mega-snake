/**
 * Publication of the action's results to the job environment.
 *
 * `core.exportVariable` is the typed equivalent of
 * `echo "KEY=value" >> "$GITHUB_ENV"`; keeping it here means the rest of the
 * code returns values instead of writing them.
 */

import * as core from "@actions/core";

import { ThreadContext } from "../models/thread-context";

/**
 * Export the resolved thread as `THREAD_ID` and `THREAD_TYPE`.
 *
 * @param thread - The resolved thread.
 * @returns None.
 */
export function exportThread(thread: ThreadContext): void {
  core.exportVariable("THREAD_ID", String(thread.id));
  core.exportVariable("THREAD_TYPE", thread.type);
}

/**
 * Export the session-log comment id as `COMMENT_ID`.
 *
 * @param commentId - Id of the session-log comment.
 * @returns None.
 */
export function exportCommentId(commentId: number): void {
  core.exportVariable("COMMENT_ID", String(commentId));
}
