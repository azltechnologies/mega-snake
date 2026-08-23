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
 *
 * `issue` is redeclared with an optional `number`: the getter derives it from
 * the payload (`payload.issue`, then `payload.pull_request`, then the payload
 * itself), so on a malformed payload it comes back `undefined` even though the
 * SDK types it as required. Keeping the type honest is what allows the guard
 * below to exist at all.
 */
export type ThreadEvent = Pick<Context, "eventName" | "payload"> & {
  issue: Omit<Context["issue"], "number"> & { number?: number };
};

/** Message used whenever the payload carries no usable thread number. */
export const UNRESOLVED_THREAD_MESSAGE = "Could not determine thread ID.";

/**
 * Resolve the thread that triggered the workflow.
 *
 * Mirrors the `case "$EVENT_NAME:$EVENT_ACTION"` block of the shell
 * implementation: only the four supported event/action pairs are accepted,
 * anything else throws.
 *
 * @param event - The webhook event name, payload and derived issue reference.
 * @throws Error when the event is unsupported, or when the payload carries no
 *   thread number.
 * @returns The resolved thread.
 */
export function resolveThread(event: ThreadEvent): ThreadContext {
  const key = `${event.eventName}:${event.payload.action ?? ""}`;

  let type: ThreadContext["type"];
  switch (key) {
    case "issue_comment:created":
      // A comment on a PR still arrives as `issue_comment`; the payload only
      // carries `pull_request` when the issue is really a pull request.
      type = event.payload.issue?.pull_request ? "pull_request" : "issue";
      break;

    case "pull_request_review_comment:created":
    case "pull_request_review:submitted":
    case "pull_request:labeled":
      type = "pull_request";
      break;

    default:
      throw new Error(`Unsupported event: ${key}`);
  }

  // `context.issue` already picks the number out of whichever key the payload
  // uses, which is what makes a per-branch extraction redundant. It is read
  // *after* the switch on purpose: the getter throws when GITHUB_REPOSITORY is
  // missing, and reading it first would replace "Unsupported event" with that
  // diagnosis on an event we never supported anyway.
  const { number, ...repo } = event.issue;
  if (number === undefined) {
    throw new Error(UNRESOLVED_THREAD_MESSAGE);
  }

  return { issue: { id: number, ...repo }, type };
}
