/**
 * The GitHub API client type, named once.
 *
 * `@actions/github` does not export the return type of `getOctokit`, so it is
 * aliased here instead of being re-derived at every call site.
 */

import * as github from "@actions/github";

/** An authenticated Octokit instance. */
export type GitHubClient = ReturnType<typeof github.getOctokit>;
