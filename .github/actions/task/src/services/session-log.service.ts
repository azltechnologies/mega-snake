/**
 * Get-or-create logic for the session-log comment of a thread.
 *
 * This is the only place that decides whether a comment has to be created;
 * `comments.service` stays a plain API wrapper with no policy of its own.
 */

import * as core from "@actions/core";

import { ThreadContext } from "../models/thread-context";
import { createMarkerComment, findMarkerComment } from "./comments.service";
import { GitHubClient } from "./github-client";

/**
 * Return the id of the thread's session-log comment, creating it when absent.
 *
 * @param client - Authenticated GitHub client.
 * @param thread - The thread to operate on.
 * @param marker - The marker identifying the session-log comment.
 * @returns The id of the existing or newly created comment.
 */
export async function ensureSessionLogComment(
  client: GitHubClient,
  thread: ThreadContext,
  marker: string,
): Promise<number> {
  core.info(`Searching for comment with marker: ${marker}`);

  const existing = await findMarkerComment(client, thread, marker);
  if (existing !== undefined) {
    core.info(`Found comment ID: ${existing}`);
    return existing;
  }

  core.info(`No comment found with marker: ${marker}\ncreating a new comment...`);
  const created = await createMarkerComment(client, thread, marker);
  core.info(`Created comment ID: ${created}`);
  return created;
}
