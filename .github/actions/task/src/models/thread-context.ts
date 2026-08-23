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

/** A GitHub repository, already split into its two halves. */
interface Repository {
  owner: string;
  repo: string;
}

/** The thread that triggered the workflow. */
export interface ThreadContext {
  repository: Repository;
  id: number;
  type: ThreadType;
}
