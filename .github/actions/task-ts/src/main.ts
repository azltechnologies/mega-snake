/**
 * TypeScript port of the composite `task` action.
 *
 * Step 1 - resolve which thread (issue or pull request) triggered the workflow.
 * Step 2 - make sure the session-log comment exists on that thread.
 *
 * Both steps export their results with `core.exportVariable`, which is the
 * typed equivalent of `echo "KEY=value" >> "$GITHUB_ENV"`.
 */

import * as core from "@actions/core";
import * as github from "@actions/github";
import { ThreadContext } from "./models/thread-context";


/** Marker prefix shared with the shell implementation. */
const MARKER_PREFIX = "<!-- mgsnake-session-log:";

/**
 * Resolve the thread that triggered the workflow.
 *
 * Mirrors the `case "$EVENT_NAME:$EVENT_ACTION"` block: only the four
 * supported event/action pairs are accepted, anything else fails the action.
 */
function resolveThread(): ThreadContext {
  const { eventName, payload } = github.context;
  const key = `${eventName}:${payload.action ?? ""}`;
  const [owner, repo] = core.getInput("repo", { required: true }).split("/");

  switch (key) {
    case "issue_comment:created": {
      const issue = payload.issue;
      if (!issue) {
        throw new Error("Could not determine thread ID.");
      }
      return {
        repository: { owner, repo },
        id: issue.number,
        // A comment on a PR still arrives as `issue_comment`; the payload only
        // carries `pull_request` when the issue is really a pull request.
        type: issue.pull_request ? "pull_request" : "issue",
      };
    }

    case "pull_request_review_comment:created":
    case "pull_request_review:submitted":
    case "pull_request:labeled": {
      const number = payload.pull_request?.number;
      if (number === undefined) {
        throw new Error("Could not determine thread ID.");
      }
      return {
        repository: { owner, repo },
        id: number,
        type: "pull_request",
      };
    }

    default:
      throw new Error(`Unsupported event: ${key}`);
  }
}

/**
 * Return the id of the last comment whose first line equals `marker`,
 * or `undefined` when no such comment exists.
 *
 * The equality is on the *first line only*, and the last match wins -
 * exactly what `awk '$2 == m' | tail -n 1` did.
 */
async function findMarkerComment(
  octokit: ReturnType<typeof github.getOctokit>,
  owner: string,
  repo: string,
  issueNumber: number,
  marker: string,
): Promise<number | undefined> {
  const comments = await octokit.paginate(
    octokit.rest.issues.listComments,
    { owner, repo, issue_number: issueNumber, per_page: 100 },
  );

  let found: number | undefined;
  for (const comment of comments) {
    const firstLine = (comment.body ?? "").split("\n")[0].replace(/\r$/, "");
    if (firstLine === marker) {
      found = comment.id;
    }
  }
  return found;
}

/** Entry point. */
async function run(): Promise<void> {
  const thread = resolveThread();
  core.exportVariable("THREAD_ID", String(thread.id));
  core.exportVariable("THREAD_TYPE", thread.type);

  const token = core.getInput("token", { required: true });
  
  const marker = `${MARKER_PREFIX}${thread.type}/${thread.id} -->`;
  const octokit = github.getOctokit(token);

  core.info(`Searching for comment with marker: ${marker}`);
  let commentId = await findMarkerComment(octokit, thread.repository.owner, thread.repository.repo, thread.id, marker);

  if (commentId !== undefined) {
    core.info(`Found comment ID: ${commentId}`);
  } else {
    core.info(`No comment found with marker: ${marker}\ncreating a new comment...`);
    const created = await octokit.rest.issues.createComment({
      owner: thread.repository.owner,
      repo: thread.repository.repo,
      issue_number: thread.id,
      body: marker,
    });
    commentId = created.data.id;
    core.info(`Created comment ID: ${commentId}`);
  }

  core.exportVariable("COMMENT_ID", String(commentId));
}

run().catch((error: unknown) => {
  // `setFailed` prints `::error::<message>` and sets the exit code to 1,
  // which is what `echo "::error::..." && exit 1` did in the shell version.
  core.setFailed(error instanceof Error ? error.message : String(error));
});
