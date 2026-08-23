/**
 * Tests for the job-environment exports.
 *
 * Every value written to `$GITHUB_ENV` is consumed by a later step, so the
 * tests pin the exact variable names, the exact stringified values and the
 * exact number of writes - an extra one would leak a variable no step expects.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import * as core from "@actions/core";

import { exportCommentId, exportThread } from "../../config/outputs";
import { threadOf } from "../helpers";

vi.mock("@actions/core", () => ({ exportVariable: vi.fn() }));

/**
 * The `exportVariable` calls recorded so far.
 *
 * @returns One `[name, value]` pair per call, in order.
 */
function exported(): unknown[][] {
  return vi.mocked(core.exportVariable).mock.calls;
}

describe("exportThread", () => {
  beforeEach(() => {
    vi.mocked(core.exportVariable).mockReset();
  });

  it("exports the id and the type as strings, and nothing else", () => {
    exportThread(threadOf("pull_request", 42));

    expect(exported()).toEqual([
      ["THREAD_ID", "42"],
      ["THREAD_TYPE", "pull_request"],
    ]);
  });

  it("never exports the repository, which the later steps read from the runner", () => {
    exportThread(threadOf("issue", 42));

    const names = exported().map(([name]) => name);
    expect(names).toEqual(["THREAD_ID", "THREAD_TYPE"]);
    expect(names).not.toContain("REPOSITORY");
  });

  it.each([
    { type: "issue" as const, id: 1 },
    { type: "pull_request" as const, id: 987654 },
    { type: "issue" as const, id: 0 },
  ])("stringifies the $type id $id rather than exporting a number", ({ type, id }) => {
    exportThread(threadOf(type, id));

    const [, value] = exported()[0];
    // Id 0 is the case that separates `String(id)` from `id || ""`: the second
    // would export an empty THREAD_ID and the next step would address the repo
    // instead of the thread.
    expect(value).toBe(String(id));
    expect(typeof value).toBe("string");
  });

  it.each([
    { type: "issue" as const },
    { type: "pull_request" as const },
  ])("exports $type as THREAD_TYPE verbatim", ({ type }) => {
    exportThread(threadOf(type, 42));

    expect(exported()[1]).toEqual(["THREAD_TYPE", type]);
  });

  it("propagates a failure to write the environment file", () => {
    // `exportVariable` writes to $GITHUB_ENV; a failure there means every later
    // step reads a stale value, so it must not be swallowed.
    const failure = new Error("EACCES: permission denied, open '/github/env'");
    vi.mocked(core.exportVariable).mockImplementationOnce(() => {
      throw failure;
    });

    expect(() => exportThread(threadOf("issue", 42))).toThrowError(failure);
    expect(exported()).toHaveLength(1);
  });
});

describe("exportCommentId", () => {
  beforeEach(() => {
    vi.mocked(core.exportVariable).mockReset();
  });

  it("exports COMMENT_ID as a string", () => {
    exportCommentId(4321);

    expect(exported()).toEqual([["COMMENT_ID", "4321"]]);
  });

  it("exports comment id 0 as \"0\", not as an empty value", () => {
    exportCommentId(0);

    expect(exported()).toEqual([["COMMENT_ID", "0"]]);
  });

  it("propagates a failure to write the environment file", () => {
    const failure = new Error("EACCES: permission denied, open '/github/env'");
    vi.mocked(core.exportVariable).mockImplementationOnce(() => {
      throw failure;
    });

    expect(() => exportCommentId(4321)).toThrowError(failure);
  });
});
