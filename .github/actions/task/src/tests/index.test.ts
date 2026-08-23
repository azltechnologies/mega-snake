/**
 * Tests for the process-level bootstrap.
 *
 * This is the only place that turns a rejection into a failed job, so it is
 * the last thing that should go untested: everything it swallows or mangles
 * reaches the user as a green run, or as a message with no cause in it.
 *
 * The module runs its work on import, so each test re-imports it with a fresh
 * module registry and then lets the floating promise settle.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import * as core from "@actions/core";

import { run } from "../main";

vi.mock("@actions/core", () => ({ setFailed: vi.fn() }));
vi.mock("../main", () => ({ run: vi.fn() }));

/**
 * Import the entry point fresh and wait for its `catch` handler to run.
 *
 * The handler is a microtask, not a timer, so draining the microtask queue is
 * both sufficient and immune to a future `vi.useFakeTimers()` in this file.
 *
 * @returns None.
 */
async function bootstrap(): Promise<void> {
  vi.resetModules();
  await import("../index");
  await Promise.resolve();
  await Promise.resolve();
}

describe("bootstrap", () => {
  beforeEach(() => {
    vi.mocked(core.setFailed).mockReset();
    vi.mocked(run).mockReset();
  });

  it("runs the action", async () => {
    vi.mocked(run).mockResolvedValue(undefined);

    await bootstrap();

    expect(run).toHaveBeenCalledTimes(1);
  });

  it("leaves the job green when the run succeeds", async () => {
    vi.mocked(run).mockResolvedValue(undefined);

    await bootstrap();

    expect(core.setFailed).not.toHaveBeenCalled();
  });

  it("fails the job with the error message alone", async () => {
    // `setFailed(error)` would print `Error: boom` plus the stack into the
    // annotation; the shell version printed the message only.
    vi.mocked(run).mockRejectedValue(new Error("Could not determine thread ID."));

    await bootstrap();

    expect(core.setFailed).toHaveBeenCalledTimes(1);
    expect(core.setFailed).toHaveBeenCalledWith("Could not determine thread ID.");
  });

  it("reports the message of a subclassed error, not its class name", async () => {
    class HttpError extends Error {}
    vi.mocked(run).mockRejectedValue(new HttpError("rate limit exceeded"));

    await bootstrap();

    expect(core.setFailed).toHaveBeenCalledWith("rate limit exceeded");
  });

  it.each([
    { name: "a thrown string", thrown: "octokit exploded", expected: "octokit exploded" },
    { name: "a thrown object", thrown: { status: 401 }, expected: "[object Object]" },
    { name: "a thrown undefined", thrown: undefined, expected: "undefined" },
  ])("fails the job on $name rather than passing a non-string on", async ({ thrown, expected }) => {
    // Anything can be thrown in JavaScript, and `setFailed` is typed for a
    // string; a raw object would reach the annotation as an empty message.
    vi.mocked(run).mockRejectedValue(thrown);

    await bootstrap();

    expect(core.setFailed).toHaveBeenCalledWith(expected);
    expect(typeof vi.mocked(core.setFailed).mock.calls[0][0]).toBe("string");
  });
});
