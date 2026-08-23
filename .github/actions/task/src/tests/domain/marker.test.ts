/**
 * Tests for the session-log marker construction.
 *
 * The marker is matched by *exact string equality* on a comment's first line,
 * so these tests compare full strings and assert that near-misses differ.
 */

import { describe, expect, it } from "vitest";

import { buildMarker, MARKER_PREFIX, MARKER_SUFFIX } from "../../domain/marker";
import { OTHER_REPOSITORY, threadOf } from "../helpers";

describe("buildMarker", () => {
  it.each([
    { type: "issue" as const, id: 42, expected: "<!-- mgsnake-session-log:issue/42 -->" },
    { type: "pull_request" as const, id: 7, expected: "<!-- mgsnake-session-log:pull_request/7 -->" },
    { type: "issue" as const, id: 0, expected: "<!-- mgsnake-session-log:issue/0 -->" },
  ])("renders $type/$id as its exact marker", ({ type, id, expected }) => {
    expect(buildMarker(threadOf(type, id))).toBe(expected);
  });

  it("is a single line, so it can be compared against a comment's first line", () => {
    const marker = buildMarker(threadOf("issue", 42));

    expect(marker.split("\n")).toHaveLength(1);
    expect(marker.startsWith(MARKER_PREFIX)).toBe(true);
    expect(marker.endsWith(MARKER_SUFFIX)).toBe(true);
  });

  it("stays an HTML comment, so it renders as nothing in the thread", () => {
    const marker = buildMarker(threadOf("issue", 42));

    expect(marker.startsWith("<!--")).toBe(true);
    expect(marker.endsWith("-->")).toBe(true);
    expect(marker).not.toContain("-->\n");
  });

  it("gives an issue and a pull request with the same number different markers", () => {
    expect(buildMarker(threadOf("issue", 42))).not.toBe(buildMarker(threadOf("pull_request", 42)));
  });

  it("never makes one thread's marker a prefix of another's", () => {
    // Without the closing suffix, `.../issue/4` would prefix `.../issue/42`,
    // and a search comparing prefixes would match the wrong thread.
    const shorter = buildMarker(threadOf("issue", 4));
    const longer = buildMarker(threadOf("issue", 42));

    expect(longer.startsWith(shorter)).toBe(false);
    expect(shorter.startsWith(longer)).toBe(false);
  });

  it("ignores the repository, since the search is already scoped to one thread", () => {
    // Two repositories cannot share a comment list, so encoding the repository
    // would only make the marker of an existing session log unmatchable after
    // a repository rename.
    const here = buildMarker(threadOf("issue", 42));
    const elsewhere = buildMarker(threadOf("issue", 42, OTHER_REPOSITORY));

    expect(elsewhere).toBe(here);
    expect(elsewhere).not.toContain(OTHER_REPOSITORY.owner);
  });
});
