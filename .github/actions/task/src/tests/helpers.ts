/**
 * Shared test helpers and fixtures.
 *
 * Keeps the stub construction and the fixture values in one place: a change to
 * the client surface, to the repository or to the marker then breaks in a
 * single file instead of in six, and no test has to restate a literal that
 * another test already owns.
 */

import { vi } from "vitest";

import { ThreadEvent } from "../domain/thread-resolver";
import { ThreadContext } from "../models/thread-context";
import { GitHubClient } from "../services/github-client";

type ThreadType = ThreadContext["type"];
type Repository = ThreadContext["repository"];

/** The repository every fixture resolves against unless it passes its own. */
export const REPOSITORY: Repository = { owner: "azltechnologies", repo: "unix-scripts" };

/**
 * A second repository, used to prove a value was *propagated* rather than
 * matched against `REPOSITORY`. Never make the two equal.
 */
export const OTHER_REPOSITORY: Repository = { owner: "someone", repo: "else" };

/**
 * A marker line for the tests that only need *a* marker.
 *
 * Its construction is pinned in `domain/marker.test.ts`; everywhere else the
 * marker is an opaque string compared for exact equality, so the literal must
 * not be rebuilt per file.
 */
export const MARKER = "<!-- mgsnake-session-log:issue/42 -->";

/** A comment as far as the marker search is concerned. */
interface StubComment {
  id: number;
  body?: string | null;
}

/** The stubbed client plus direct handles on its spies. */
export interface StubClient {
  client: GitHubClient;
  paginate: ReturnType<typeof vi.fn>;
  listComments: ReturnType<typeof vi.fn>;
  createComment: ReturnType<typeof vi.fn>;
}

/**
 * Build a GitHub client stub returning `comments` from the paginated list.
 *
 * The spies are returned alongside the client so a test can override them
 * (`paginate.mockRejectedValueOnce(...)`) to exercise an API failure.
 *
 * @param comments - Comments the list endpoint should yield.
 * @param createdId - Id the create endpoint should report.
 * @returns The stub client and its spies.
 */
export function stubGitHubClient(comments: StubComment[], createdId = 999): StubClient {
  const listComments = vi.fn();
  const createComment = vi.fn(async () => ({ data: { id: createdId } }));
  const paginate = vi.fn(async () => comments);

  const client = {
    paginate,
    rest: { issues: { listComments, createComment } },
  } as unknown as GitHubClient;

  return { client, paginate, listComments, createComment };
}

/**
 * Build a thread context.
 *
 * @param type - Thread kind.
 * @param id - Thread number.
 * @param repository - Repository owning the thread.
 * @returns The thread context.
 */
export function threadOf(
  type: ThreadType,
  id: number,
  repository: Repository = REPOSITORY,
): ThreadContext {
  return { repository, id, type };
}

/**
 * Build a webhook event for the resolver.
 *
 * The payload is typed loosely and cast once, here: the runner hands it over
 * as parsed JSON, so the negative tests have to express payloads that
 * `WebhookPayload` forbids (an `issue` without a `number`, for instance).
 * Keeping the cast in the builder is what stops it from spreading.
 *
 * @param eventName - Value of `GITHUB_EVENT_NAME`.
 * @param payload - The webhook payload, as the runner would deliver it.
 * @param repo - Repository the workflow is running in.
 * @returns The event slice `resolveThread` consumes.
 */
export function eventOf(
  eventName: string,
  payload: Record<string, unknown>,
  repo: Repository = REPOSITORY,
): ThreadEvent {
  return { eventName, payload: payload as ThreadEvent["payload"], repo };
}
