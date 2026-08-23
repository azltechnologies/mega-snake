/**
 * Construction of the session-log comment marker.
 *
 * The marker is an HTML comment, so it is invisible in the rendered thread
 * while still being the first line of the comment body - which is what makes
 * it findable without any server-side state.
 */

import { ThreadContext } from "../models/thread-context";

/** Marker prefix shared with the shell implementation. */
export const MARKER_PREFIX = "<!-- mgsnake-session-log:";

/** Marker suffix closing the HTML comment. */
export const MARKER_SUFFIX = " -->";

/**
 * Build the marker identifying the session-log comment of a thread.
 *
 * @param thread - The thread the marker belongs to.
 * @returns The marker line, e.g. `<!-- mgsnake-session-log:issue/42 -->`.
 */
export function buildMarker(thread: ThreadContext): string {
  return `${MARKER_PREFIX}${thread.type}/${thread.issue.id}${MARKER_SUFFIX}`;
}
