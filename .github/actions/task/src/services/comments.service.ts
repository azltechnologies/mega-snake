/**
 * Thin wrapper over the GitHub issue-comment endpoints.
 *
 * Every function takes the client as a parameter rather than building one, so
 * the calling code owns authentication and tests can inject a stub.
 */

import { ThreadContext } from "../models/thread-context";
import { GitHubClient } from "./github-client";

/**
 * Find the last comment whose first line equals `marker`.
 *
 * The equality is on the *first line only*, and the last match wins - exactly
 * what `awk '$2 == m' | tail -n 1` did in the shell implementation.
 *
 * @param client - Authenticated GitHub client.
 * @param context - Thread whose comments are searched; supplies the repository
 *   and the issue number.
 * @param marker - The exact first line to look for.
 * @throws Error when the list endpoint fails; the failure is not swallowed.
 * @returns The comment id, or `undefined` when no comment matches.
 */
export async function findMarkerComment(
  client: GitHubClient,
  context: ThreadContext,
  marker: string,
): Promise<number | undefined> {
  const { repository, id: issue_number } = context;
  const comments = await client.paginate(client.rest.issues.listComments, {
    ...repository,
    issue_number,
    per_page: 100,
  });

  let found: number | undefined;
  for (const comment of comments) {
    const firstLine = (comment.body ?? "").split("\n")[0].replace(/\r$/, "");
    if (firstLine === marker) {
      found = comment.id;
    }
  }
  return found;
}

/**
 * Create a comment whose body is the marker itself.
 *
 * @param client - Authenticated GitHub client.
 * @param context - Thread the comment is created on; supplies the repository
 *   and the issue number.
 * @param marker - The marker to use as the comment body.
 * @throws Error when the create endpoint fails.
 * @returns The id of the created comment.
 */
export async function createMarkerComment(
  client: GitHubClient,
  context: ThreadContext,
  marker: string,
): Promise<number> {
  const { repository, id: issue_number } = context;
  const created = await client.rest.issues.createComment({
    ...repository,
    issue_number,
    body: marker,
  });
  return created.data.id;
}
