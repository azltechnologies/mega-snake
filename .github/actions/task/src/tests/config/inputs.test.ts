/**
 * Tests for input reading.
 *
 * The point of this module is that `token` is *required*, so the tests assert
 * the option object reaching `core.getInput` and what happens when the runtime
 * refuses the read - not just the returned value on the happy path.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import * as core from "@actions/core";

import { readInputs } from "../../config/inputs";

vi.mock("@actions/core", () => ({ getInput: vi.fn() }));

describe("readInputs", () => {
  beforeEach(() => {
    vi.mocked(core.getInput).mockReset();
  });

  it("reads the token and marks it required", () => {
    vi.mocked(core.getInput).mockReturnValue("ghs_token");

    expect(readInputs()).toEqual({ token: "ghs_token" });
    expect(core.getInput).toHaveBeenCalledTimes(1);
    expect(core.getInput).toHaveBeenCalledWith("token", { required: true });
  });

  it("returns the token verbatim, without rewriting it", () => {
    // `core.getInput` already trims; doing it again here would corrupt a token
    // format that legitimately contains the character being stripped.
    const raw = "ghs_AbC-123_xyz";
    vi.mocked(core.getInput).mockReturnValue(raw);

    expect(readInputs().token).toBe(raw);
  });

  it("propagates the failure when the required token is missing", () => {
    // This is what `core.getInput(..., { required: true })` does on an empty
    // input. Defaulting to "" here would push the failure to the first API
    // call, where it surfaces as an opaque 401 instead.
    const missing = new Error("Input required and not supplied: token");
    vi.mocked(core.getInput).mockImplementation(() => {
      throw missing;
    });

    expect(() => readInputs()).toThrowError(missing);
  });

  it("never substitutes a default for an empty token", () => {
    // A runtime that hands back "" instead of throwing must not be papered
    // over: an empty token authenticates as nobody and fails much later.
    vi.mocked(core.getInput).mockReturnValue("");

    expect(readInputs()).toEqual({ token: "" });
  });
});
