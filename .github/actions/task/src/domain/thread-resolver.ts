/**
 * Resolution of the thread that triggered the workflow.
 *
 * A pure mapping from a webhook event to a `ThreadContext`: it performs no
 * I/O and reads no inputs, so every supported event/action pair can be
 * covered with plain object literals.
 */

import type { Context } from "@actions/github/lib/context";

import { ThreadContext } from "../models/thread-context";

/**
 * The slice of `github.context` this resolver needs.
 *
 * Declared structurally rather than importing `Context` so a test can pass a
 * literal instead of instantiating the real class.
 */
export type ThreadEvent = Pick<Context, "eventName" | "payload" | "repo">;

/** Message used whenever the payload carries no usable thread number. */
export const UNRESOLVED_THREAD_MESSAGE = "Could not determine thread ID.";

/**
 * The part of a payload entry that carries the thread number.
 *
 * `number` is optional here even though `WebhookPayload` declares it required:
 * the payload is JSON the runner parsed, so the type is a promise, not a
 * guarantee.
 */
type NumberedThread = { number?: number } | undefined;

/**
 * Read the thread number out of an `issue` or `pull_request` payload entry.
 *
 * @param source - The payload entry, possibly absent.
 * @throws Error when the entry is absent or carries no number.
 * @returns The thread number.
 */
function requireThreadNumber(source: NumberedThread): number {
  const number = source?.number;
  // Explicitly against `undefined`: pull request #0 does not exist, but a
  // truthiness check would also reject a legitimately parsed 0.
  if (number === undefined) {
    throw new Error(UNRESOLVED_THREAD_MESSAGE);
  }
  return number;
}

/**
 * Resolve the thread that triggered the workflow.
 *
 * Mirrors the `case "$EVENT_NAME:$EVENT_ACTION"` block of the shell
 * implementation: only the four supported event/action pairs are accepted,
 * anything else throws.
 *
 * @param event - The webhook event name, payload and repository.
 * @throws Error when the event is unsupported, or when the payload carries no
 *   thread number.
 * @returns The resolved thread.
 */
export function resolveThread(event: ThreadEvent): ThreadContext {
  const key = `${event.eventName}:${event.payload.action ?? ""}`;

  switch (key) {
    case "issue_comment:created": {
      const issue = event.payload.issue;
      return {
        repository: event.repo,
        id: requireThreadNumber(issue),
        // A comment on a PR still arrives as `issue_comment`; the payload only
        // carries `pull_request` when the issue is really a pull request.
        type: issue?.pull_request ? "pull_request" : "issue",
      };
    }

    case "pull_request_review_comment:created":
    case "pull_request_review:submitted":
    case "pull_request:labeled":
      return {
        repository: event.repo,
        id: requireThreadNumber(event.payload.pull_request),
        type: "pull_request",
      };

    default:
      throw new Error(`Unsupported event: ${key}`);
  }
}
