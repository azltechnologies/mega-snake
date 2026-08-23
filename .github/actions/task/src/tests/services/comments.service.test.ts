/**
 * Tests for the issue-comment API wrapper.
 *
 * The search contract is narrow and easy to get subtly wrong: equality on the
 * *first line only*, and the *last* match wins. Each of those two clauses gets
 * a test that fails if only the other one is implemented.
 *
 * Every request assertion derives its coordinates from the thread that was
 * passed in, so a wrapper that sent a repository of its own would fail here
 * instead of matching a literal that happens to agree.
 */

import { describe, expect, it } from "vitest";

import { createMarkerComment, findMarkerComment } from "../../services/comments.service";
import { MARKER, OTHER_REPOSITORY, stubGitHubClient, threadOf } from "../helpers";

/** The thread every search runs against unless a test needs another. */
const THREAD = threadOf("issue", 42);

describe("findMarkerComment", () => {
  it("returns undefined when the thread has no comments at all", async () => {
    const { client } = stubGitHubClient([]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBeUndefined();
  });

  it("returns undefined when no comment matches", async () => {
    const { client } = stubGitHubClient([
      { id: 1, body: "just a comment" },
      { id: 2, body: "<!-- mgsnake-session-log:issue/43 -->" },
    ]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBeUndefined();
  });

  it("returns the id of the only matching comment", async () => {
    const { client } = stubGitHubClient([
      { id: 1, body: "noise" },
      { id: 2, body: `${MARKER}\nsession log body` },
    ]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBe(2);
  });

  it("returns the last match, not the first, when several comments carry the marker", async () => {
    const { client } = stubGitHubClient([
      { id: 10, body: MARKER },
      { id: 20, body: MARKER },
      { id: 30, body: MARKER },
    ]);

    const found = await findMarkerComment(client, THREAD, MARKER);

    expect(found).toBe(30);
    expect(found).not.toBe(10);
  });

  it("ignores a marker that is not on the first line", async () => {
    const { client } = stubGitHubClient([{ id: 5, body: `quoting a log:\n${MARKER}` }]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBeUndefined();
  });

  it("requires the whole first line to equal the marker, not merely contain it", async () => {
    const { client } = stubGitHubClient([
      { id: 6, body: `prefix ${MARKER}` },
      { id: 7, body: `${MARKER} trailing` },
    ]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBeUndefined();
  });

  it("compares the first line case-sensitively", async () => {
    const { client } = stubGitHubClient([{ id: 11, body: MARKER.toUpperCase() }]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBeUndefined();
  });

  it("matches a first line terminated by CRLF", async () => {
    const { client } = stubGitHubClient([{ id: 8, body: `${MARKER}\r\nbody` }]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBe(8);
  });

  it("strips only the trailing carriage return, not one inside the line", async () => {
    const { client } = stubGitHubClient([{ id: 12, body: `${MARKER}\r ignored\nbody` }]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBeUndefined();
  });

  it.each([
    { name: "a null body", body: null },
    { name: "an absent body", body: undefined },
  ])("treats $name as an empty string instead of throwing", async ({ body }) => {
    const { client } = stubGitHubClient([{ id: 9, body }]);

    await expect(findMarkerComment(client, THREAD, MARKER)).resolves.toBeUndefined();
  });

  it("paginates the list endpoint with the thread's own coordinates", async () => {
    const { client, paginate, listComments } = stubGitHubClient([]);

    await findMarkerComment(client, THREAD, MARKER);

    expect(paginate).toHaveBeenCalledTimes(1);
    expect(paginate).toHaveBeenCalledWith(listComments, {
      owner: THREAD.issue.owner,
      repo: THREAD.issue.repo,
      issue_number: THREAD.issue.id,
      per_page: 100,
    });
  });

  it("sends the repository it was handed, not a default one", async () => {
    const thread = threadOf("issue", 42, OTHER_REPOSITORY);
    const { client, paginate, listComments } = stubGitHubClient([]);

    await findMarkerComment(client, thread, MARKER);

    expect(paginate).toHaveBeenCalledWith(listComments, {
      ...OTHER_REPOSITORY,
      issue_number: 42,
      per_page: 100,
    });
    expect(paginate).not.toHaveBeenCalledWith(
      listComments,
      expect.objectContaining({ owner: THREAD.issue.owner }),
    );
  });

  it("reads a pull request through the issue-comments endpoint too", async () => {
    // GitHub exposes PR conversation comments as issue comments; querying the
    // review-comment endpoint instead would silently find nothing.
    const pull = threadOf("pull_request", 9);
    const { client, paginate, listComments } = stubGitHubClient([]);

    await findMarkerComment(client, pull, MARKER);

    expect(paginate).toHaveBeenCalledWith(listComments, {
      owner: pull.issue.owner,
      repo: pull.issue.repo,
      issue_number: 9,
      per_page: 100,
    });
  });

  it("propagates an API failure instead of reporting 'not found'", async () => {
    // Swallowing this would post a duplicate session log on every rate-limited
    // run, since the caller reads `undefined` as "no comment exists yet".
    const { client, paginate } = stubGitHubClient([]);
    paginate.mockRejectedValueOnce(new Error("HttpError: rate limit exceeded"));

    await expect(findMarkerComment(client, THREAD, MARKER)).rejects.toThrowError(
      new Error("HttpError: rate limit exceeded"),
    );
  });
});

describe("createMarkerComment", () => {
  it("posts the marker as the whole body and returns the new id", async () => {
    const { client, createComment } = stubGitHubClient([], 4321);

    const created = await createMarkerComment(client, THREAD, MARKER);

    expect(created).toBe(4321);
    expect(createComment).toHaveBeenCalledTimes(1);
    expect(createComment).toHaveBeenCalledWith({
      owner: THREAD.issue.owner,
      repo: THREAD.issue.repo,
      issue_number: THREAD.issue.id,
      body: MARKER,
    });
  });

  it("posts to the repository and thread it was handed, not a default one", async () => {
    const pull = threadOf("pull_request", 9, OTHER_REPOSITORY);
    const { client, createComment } = stubGitHubClient([], 4321);

    await createMarkerComment(client, pull, MARKER);

    expect(createComment).toHaveBeenCalledWith({
      ...OTHER_REPOSITORY,
      issue_number: 9,
      body: MARKER,
    });
  });

  it("propagates a create failure", async () => {
    const { client, createComment } = stubGitHubClient([]);
    createComment.mockRejectedValueOnce(new Error("HttpError: Resource not accessible by integration"));

    await expect(createMarkerComment(client, THREAD, MARKER)).rejects.toThrowError(
      new Error("HttpError: Resource not accessible by integration"),
    );
  });
});
