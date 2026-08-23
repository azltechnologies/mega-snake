/**
 * Tests for the get-or-create policy of the session-log comment.
 *
 * The whole value of this layer is that it creates a comment *only* when none
 * exists, so every test asserts the call count of the endpoint it must not
 * hit - including the failure paths, where a duplicate comment is the damage
 * a swallowed error would cause.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import * as core from "@actions/core";

import { ensureSessionLogComment } from "../../services/session-log.service";
import { MARKER, stubGitHubClient, threadOf } from "../helpers";

vi.mock("@actions/core", () => ({ info: vi.fn() }));

/** The thread the policy runs against unless a test needs another. */
const THREAD = threadOf("issue", 42);

/**
 * The messages `core.info` received, joined for substring-free inspection.
 *
 * @returns One string per logged line.
 */
function loggedLines(): string[] {
  return vi.mocked(core.info).mock.calls.map(([message]) => message);
}

describe("ensureSessionLogComment", () => {
  beforeEach(() => {
    vi.mocked(core.info).mockReset();
  });

  it("reuses the existing comment and creates nothing", async () => {
    const { client, createComment } = stubGitHubClient([{ id: 77, body: MARKER }]);

    const id = await ensureSessionLogComment(client, THREAD, MARKER);

    expect(id).toBe(77);
    expect(createComment).not.toHaveBeenCalled();
  });

  it("reuses comment id 0 rather than treating it as absent", async () => {
    // `existing !== undefined` accepts it; a truthiness check would post a
    // second session log over the top of a perfectly good one.
    const { client, createComment } = stubGitHubClient([{ id: 0, body: MARKER }]);

    const id = await ensureSessionLogComment(client, THREAD, MARKER);

    expect(id).toBe(0);
    expect(createComment).not.toHaveBeenCalled();
  });

  it("creates the comment when none carries the marker", async () => {
    const { client, createComment } = stubGitHubClient([{ id: 1, body: "noise" }], 555);
    const pull = threadOf("pull_request", 9);

    const id = await ensureSessionLogComment(client, pull, MARKER);

    expect(id).toBe(555);
    expect(createComment).toHaveBeenCalledTimes(1);
    expect(createComment).toHaveBeenCalledWith({
      owner: pull.issue.owner,
      repo: pull.issue.repo,
      issue_number: 9,
      body: MARKER,
    });
  });

  it("searches with the marker it was given, on the thread it was given", async () => {
    const { client, paginate, listComments } = stubGitHubClient([{ id: 77, body: MARKER }]);

    await ensureSessionLogComment(client, THREAD, MARKER);

    expect(paginate).toHaveBeenCalledWith(listComments, {
      owner: THREAD.issue.owner,
      repo: THREAD.issue.repo,
      issue_number: THREAD.issue.id,
      per_page: 100,
    });
  });

  it("reports the id it found, so the job log names the comment it reused", async () => {
    const { client } = stubGitHubClient([{ id: 77, body: MARKER }]);

    await ensureSessionLogComment(client, THREAD, MARKER);

    expect(loggedLines()).toContain("Found comment ID: 77");
    expect(loggedLines()).not.toContain("Created comment ID: 77");
  });

  it("reports the id it created, so the job log names the new comment", async () => {
    const { client } = stubGitHubClient([], 555);

    await ensureSessionLogComment(client, THREAD, MARKER);

    expect(loggedLines()).toContain("Created comment ID: 555");
    expect(loggedLines()).not.toContain("Found comment ID: 555");
  });

  it("propagates a search failure without creating a comment", async () => {
    // Falling through to `create` here is how a rate-limited run ends up with
    // a second session log on the same thread.
    const { client, paginate, createComment } = stubGitHubClient([]);
    paginate.mockRejectedValueOnce(new Error("HttpError: rate limit exceeded"));

    await expect(ensureSessionLogComment(client, THREAD, MARKER)).rejects.toThrowError(
      new Error("HttpError: rate limit exceeded"),
    );
    expect(createComment).not.toHaveBeenCalled();
  });

  it("propagates a create failure instead of returning an id nobody can use", async () => {
    const { client, createComment } = stubGitHubClient([]);
    createComment.mockRejectedValueOnce(new Error("HttpError: Resource not accessible by integration"));

    await expect(ensureSessionLogComment(client, THREAD, MARKER)).rejects.toThrowError(
      new Error("HttpError: Resource not accessible by integration"),
    );
  });
});
