/**
 * Domain types describing the thread (issue or pull request) an action run
 * operates on.
 *
 * This module is deliberately free of `@actions/*` imports: it must stay a
 * plain data shape so the domain layer can be exercised without a GitHub
 * Actions runtime.
 */

/** The two kinds of thread a workflow event can point at. */
type ThreadType = "issue" | "pull_request";

/**
 * A thread reference: the repository, split into its two halves, plus the
 * number that addresses the thread inside it.
 *
 * Named after `context.issue`, which is where it comes from and which uses the
 * same shape for a pull request - GitHub addresses PR conversation comments
 * through the issue endpoints.
 */
export interface Issue {
  /** Account or organisation owning the repository. */
  owner: string;
  /** Repository name. */
  repo: string;
  /** Issue or pull request number. */
  id: number;
}

/** The thread that triggered the workflow. */
export interface ThreadContext {
  issue: Issue;
  type: ThreadType;
}
