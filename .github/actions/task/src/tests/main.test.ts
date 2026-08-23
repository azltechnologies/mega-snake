/**
 * Tests for the composition root.
 *
 * These do not re-test the layers - they pin the *wiring*: that the resolved
 * thread is exported before the API work, that the marker handed to the
 * service is the one built from that thread, and that the comment id reaching
 * the environment is the one the service returned.
 *
 * Each failure mode gets its own test, because the interesting part of a
 * failure here is *how far the run got*: which variables the later steps will
 * find already set, and which endpoint was never reached.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import * as core from "@actions/core";
import * as github from "@actions/github";

import { UNRESOLVED_THREAD_MESSAGE } from "../domain/thread-resolver";
import { run } from "../main";
import { eventOf, OTHER_REPOSITORY, REPOSITORY, stubGitHubClient } from "./helpers";

// Hoisted above the imports, so the values are placeholders: `beforeEach`
// rewrites them from the shared fixtures once the modules have loaded.
const { mockContext } = vi.hoisted(() => ({
  mockContext: {
    eventName: "",
    payload: {} as Record<string, unknown>,
    issue: { owner: "", repo: "" } as { owner: string; repo: string; number?: number },
  },
}));

vi.mock("@actions/core", () => ({
  getInput: vi.fn(() => "ghs_token"),
  exportVariable: vi.fn(),
  info: vi.fn(),
  setFailed: vi.fn(),
}));

vi.mock("@actions/github", () => ({
  context: mockContext,
  getOctokit: vi.fn(),
}));

/**
 * A triggering event, with everything the run is expected to produce from it.
 *
 * The markers are written out in full on purpose: this is the end-to-end pin
 * of the literal the shell implementation also wrote. Its *construction* is
 * tested in `domain/marker.test.ts`.
 */
const EVENTS = [
  {
    name: "a comment on an issue",
    eventName: "issue_comment",
    payload: { action: "created", issue: { number: 42 } },
    threadId: "42",
    threadType: "issue",
    marker: "<!-- mgsnake-session-log:issue/42 -->",
  },
  {
    name: "a submitted pull request review",
    eventName: "pull_request_review",
    payload: { action: "submitted", pull_request: { number: 7 } },
    threadId: "7",
    threadType: "pull_request",
    marker: "<!-- mgsnake-session-log:pull_request/7 -->",
  },
] as const;

const [ISSUE_EVENT] = EVENTS;

/**
 * Point `github.context` at an event.
 *
 * Built through `eventOf` so the mocked context derives its `issue` from the
 * payload exactly as the real `Context` getter would; a hand-written pair
 * could describe a context the runner cannot produce.
 *
 * @param event - Event name and payload the runner would deliver.
 * @param repo - Repository the runner reports.
 * @returns None.
 */
function useEvent(
  event: { eventName: string; payload: Record<string, unknown> },
  repo: typeof REPOSITORY = REPOSITORY,
): void {
  const built = eventOf(event.eventName, event.payload, repo);

  mockContext.eventName = built.eventName;
  mockContext.payload = built.payload as Record<string, unknown>;
  mockContext.issue = { ...built.issue };
}

/**
 * Point `getOctokit` at a client whose thread carries `comments`.
 *
 * @param comments - Comments the list endpoint yields.
 * @param createdId - Id the create endpoint reports.
 * @returns The stub client and its spies.
 */
function withComments(
  comments: Array<{ id: number; body?: string | null }>,
  createdId = 4321,
): ReturnType<typeof stubGitHubClient> {
  const stub = stubGitHubClient(comments, createdId);
  vi.mocked(github.getOctokit).mockReturnValue(stub.client);
  return stub;
}

/**
 * The `exportVariable` calls recorded so far.
 *
 * @returns One `[name, value]` pair per call, in order.
 */
function exported(): unknown[][] {
  return vi.mocked(core.exportVariable).mock.calls;
}

describe("run", () => {
  beforeEach(() => {
    vi.mocked(core.exportVariable).mockReset();
    vi.mocked(core.getInput).mockReset();
    vi.mocked(github.getOctokit).mockReset();
    useEvent(ISSUE_EVENT);
  });

  it("exports the three variables in order, reusing an existing session log", async () => {
    const { createComment } = withComments([{ id: 77, body: ISSUE_EVENT.marker }]);

    await run();

    expect(exported()).toEqual([
      ["THREAD_ID", "42"],
      ["THREAD_TYPE", "issue"],
      ["COMMENT_ID", "77"],
    ]);
    expect(createComment).not.toHaveBeenCalled();
  });

  it.each(EVENTS)(
    "creates the session log for $name with the marker built from the resolved thread",
    async ({ eventName, payload, threadId, threadType, marker }) => {
      useEvent({ eventName, payload: { ...payload } });
      const { createComment } = withComments([]);

      await run();

      expect(createComment).toHaveBeenCalledWith({
        ...REPOSITORY,
        issue_number: Number(threadId),
        body: marker,
      });
      expect(exported()).toEqual([
        ["THREAD_ID", threadId],
        ["THREAD_TYPE", threadType],
        ["COMMENT_ID", "4321"],
      ]);
    },
  );

  it("addresses the repository the runner reported, not one of its own", async () => {
    useEvent(ISSUE_EVENT, OTHER_REPOSITORY);
    const { paginate, listComments } = withComments([]);

    await run();

    expect(paginate).toHaveBeenCalledWith(listComments, {
      ...OTHER_REPOSITORY,
      issue_number: 42,
      per_page: 100,
    });
    expect(paginate).not.toHaveBeenCalledWith(
      listComments,
      expect.objectContaining({ owner: REPOSITORY.owner }),
    );
  });

  it("authenticates with the token input", async () => {
    withComments([]);

    await run();

    expect(core.getInput).toHaveBeenCalledWith("token", { required: true });
    expect(github.getOctokit).toHaveBeenCalledWith("ghs_token");
  });

  it("exports the thread before touching the API, so an API failure still leaves it set", async () => {
    const { paginate } = withComments([]);
    paginate.mockRejectedValueOnce(new Error("rate limited"));

    await expect(run()).rejects.toThrowError(new Error("rate limited"));

    expect(exported()).toEqual([
      ["THREAD_ID", "42"],
      ["THREAD_TYPE", "issue"],
    ]);
  });

  it("fails without exporting anything when the event is unsupported", async () => {
    useEvent({ eventName: "push", payload: { action: "created" } });
    withComments([]);

    await expect(run()).rejects.toThrowError(new Error("Unsupported event: push:created"));

    expect(exported()).toEqual([]);
    expect(github.getOctokit).not.toHaveBeenCalled();
  });

  it("fails without exporting anything when the payload carries no thread number", async () => {
    useEvent({ eventName: "issue_comment", payload: { action: "created", issue: {} } });
    withComments([]);

    await expect(run()).rejects.toThrowError(new Error(UNRESOLVED_THREAD_MESSAGE));

    expect(exported()).toEqual([]);
    expect(github.getOctokit).not.toHaveBeenCalled();
  });

  it("fails after exporting the thread when the token input is missing", async () => {
    // The token is read *after* the thread is resolved, so the later steps can
    // still report which thread the run was about.
    const missing = new Error("Input required and not supplied: token");
    vi.mocked(core.getInput).mockImplementationOnce(() => {
      throw missing;
    });
    withComments([]);

    await expect(run()).rejects.toThrowError(missing);

    expect(exported()).toEqual([
      ["THREAD_ID", "42"],
      ["THREAD_TYPE", "issue"],
    ]);
    expect(github.getOctokit).not.toHaveBeenCalled();
  });

  it("fails when the client cannot be built from the token", async () => {
    vi.mocked(github.getOctokit).mockImplementationOnce(() => {
      throw new Error("Parameter token or opts.auth is required");
    });

    await expect(run()).rejects.toThrowError(
      new Error("Parameter token or opts.auth is required"),
    );

    expect(exported()).toEqual([
      ["THREAD_ID", "42"],
      ["THREAD_TYPE", "issue"],
    ]);
  });

  it("does not export a comment id when the comment could not be created", async () => {
    const { createComment } = withComments([]);
    createComment.mockRejectedValueOnce(new Error("Resource not accessible by integration"));

    await expect(run()).rejects.toThrowError(
      new Error("Resource not accessible by integration"),
    );

    const names = exported().map(([name]) => name);
    expect(names).toEqual(["THREAD_ID", "THREAD_TYPE"]);
    expect(names).not.toContain("COMMENT_ID");
  });
});
