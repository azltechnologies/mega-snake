/**
 * Tests for the pure event-to-thread resolution.
 *
 * The resolver's contract is a closed set of event/action pairs, so the suite
 * walks that whole set rather than sampling one case, and asserts the entire
 * returned object instead of a single field. Every rejection is asserted with
 * an exact message: the two failure branches differ only in what they say, and
 * a substring assertion would not tell them apart.
 */

import { describe, expect, it } from "vitest";

import { resolveThread, ThreadEvent, UNRESOLVED_THREAD_MESSAGE } from "../../domain/thread-resolver";
import { ThreadContext } from "../../models/thread-context";
import { eventOf, OTHER_REPOSITORY, REPOSITORY } from "../helpers";

type ThreadType = ThreadContext["type"];

/** A supported case, kept as raw parts so each test can pick the repository. */
interface SupportedCase {
  name: string;
  eventName: string;
  payload: Record<string, unknown>;
  expectedId: number;
  expectedType: ThreadType;
}

/** Every event/action pair the resolver is contracted to accept. */
const SUPPORTED: ReadonlyArray<SupportedCase> = [
  {
    name: "issue_comment:created on a plain issue",
    eventName: "issue_comment",
    payload: { action: "created", issue: { number: 42 } },
    expectedId: 42,
    expectedType: "issue",
  },
  {
    name: "issue_comment:created on a pull request",
    eventName: "issue_comment",
    payload: { action: "created", issue: { number: 7, pull_request: { url: "u" } } },
    expectedId: 7,
    expectedType: "pull_request",
  },
  {
    name: "pull_request_review_comment:created",
    eventName: "pull_request_review_comment",
    payload: { action: "created", pull_request: { number: 11 } },
    expectedId: 11,
    expectedType: "pull_request",
  },
  {
    name: "pull_request_review:submitted",
    eventName: "pull_request_review",
    payload: { action: "submitted", pull_request: { number: 12 } },
    expectedId: 12,
    expectedType: "pull_request",
  },
  {
    name: "pull_request:labeled",
    eventName: "pull_request",
    payload: { action: "labeled", pull_request: { number: 13 } },
    expectedId: 13,
    expectedType: "pull_request",
  },
];

/** The payload keys the resolver reads the thread number from. */
const NUMBER_HOLDERS: ReadonlyArray<{ name: string; eventName: string; action: string; key: string }> = [
  { name: "issue_comment:created", eventName: "issue_comment", action: "created", key: "issue" },
  {
    name: "pull_request_review_comment:created",
    eventName: "pull_request_review_comment",
    action: "created",
    key: "pull_request",
  },
  {
    name: "pull_request_review:submitted",
    eventName: "pull_request_review",
    action: "submitted",
    key: "pull_request",
  },
  { name: "pull_request:labeled", eventName: "pull_request", action: "labeled", key: "pull_request" },
];

describe("resolveThread", () => {
  it.each(SUPPORTED)(
    "resolves the whole thread context for $name",
    ({ name, eventName, payload, expectedId, expectedType }) => {
      const expected: ThreadContext = {
        repository: REPOSITORY,
        id: expectedId,
        type: expectedType,
      };

      expect(resolveThread(eventOf(eventName, payload)), `wrong thread for ${name}`).toEqual(expected);
    },
  );

  it.each(SUPPORTED)(
    "returns the repository it was given for $name, never one of its own",
    ({ name, eventName, payload }) => {
      // Resolved with a repository no other fixture uses, so a hardcoded or
      // default-valued return cannot satisfy this.
      const resolved = resolveThread(eventOf(eventName, payload, OTHER_REPOSITORY));

      expect(resolved.repository, `wrong repository for ${name}`).toEqual(OTHER_REPOSITORY);
      expect(resolved.repository, `${name} fell back to the default repository`).not.toEqual(REPOSITORY);
    },
  );

  it("distinguishes an issue comment from a pull request comment by the payload alone", () => {
    const base = { number: 42 };
    const asIssue = resolveThread(eventOf("issue_comment", { action: "created", issue: base }));
    const asPull = resolveThread(
      eventOf("issue_comment", { action: "created", issue: { ...base, pull_request: { url: "u" } } }),
    );

    expect(asIssue.type).toBe("issue");
    expect(asPull.type).toBe("pull_request");
    expect(asIssue.type).not.toBe(asPull.type);
  });

  it("reads the number from pull_request, ignoring an issue the payload also carries", () => {
    // A review payload carries both keys; reading the wrong one would point
    // the session log at an unrelated thread with no error at all.
    const resolved = resolveThread(
      eventOf("pull_request_review", {
        action: "submitted",
        pull_request: { number: 5 },
        issue: { number: 99 },
      }),
    );

    expect(resolved.id).toBe(5);
    expect(resolved.id).not.toBe(99);
    expect(resolved.type).toBe("pull_request");
  });

  it.each([
    { name: "an unknown event name", eventName: "push", action: "created" },
    { name: "an empty event name", eventName: "", action: "created" },
    { name: "a supported event with an unsupported action", eventName: "pull_request", action: "opened" },
    { name: "a supported event with a related-but-wrong action", eventName: "pull_request", action: "unlabeled" },
    { name: "issue_comment with a non-created action", eventName: "issue_comment", action: "edited" },
    { name: "issue_comment with a deleted action", eventName: "issue_comment", action: "deleted" },
    { name: "a review comment that was edited", eventName: "pull_request_review_comment", action: "edited" },
    { name: "a missing action", eventName: "pull_request", action: undefined },
  ])("rejects $name naming the offending key", ({ eventName, action }) => {
    const event: ThreadEvent = eventOf(eventName, action === undefined ? {} : { action });

    expect(() => resolveThread(event)).toThrowError(
      new Error(`Unsupported event: ${eventName}:${action ?? ""}`),
    );
  });

  it("rejects an unsupported event before it ever reads the repository", () => {
    // `github.context.repo` is a getter that throws when GITHUB_REPOSITORY is
    // unset. Reading it eagerly would replace the real diagnosis with that one.
    const event = {
      eventName: "push",
      payload: { action: "created" },
      get repo(): never {
        throw new Error("context.repo requires a GITHUB_REPOSITORY environment variable");
      },
    } as unknown as ThreadEvent;

    expect(() => resolveThread(event)).toThrowError(new Error("Unsupported event: push:created"));
  });

  it.each(NUMBER_HOLDERS)("rejects $name when the payload has no $key at all", ({ eventName, action }) => {
    expect(() => resolveThread(eventOf(eventName, { action }))).toThrowError(
      new Error(UNRESOLVED_THREAD_MESSAGE),
    );
  });

  it.each(NUMBER_HOLDERS)(
    "rejects $name when $key is present but carries no number",
    ({ eventName, action, key }) => {
      // The runner delivers parsed JSON, so a well-formed *object* with a
      // missing field is reachable even though the type forbids it. Before this
      // was checked the resolver happily returned `id: undefined`, which surfaced
      // much later as a `THREAD_ID=undefined` in the job environment.
      expect(() => resolveThread(eventOf(eventName, { action, [key]: {} }))).toThrowError(
        new Error(UNRESOLVED_THREAD_MESSAGE),
      );
    },
  );

  it.each(NUMBER_HOLDERS)("rejects $name when $key is null", ({ eventName, action, key }) => {
    expect(() => resolveThread(eventOf(eventName, { action, [key]: null }))).toThrowError(
      new Error(UNRESOLVED_THREAD_MESSAGE),
    );
  });

  it.each(NUMBER_HOLDERS)("accepts thread number 0 for $name instead of reading it as absent", ({
    eventName,
    action,
    key,
  }) => {
    // A truthiness check would reject this; only `=== undefined` accepts it.
    const resolved = resolveThread(eventOf(eventName, { action, [key]: { number: 0 } }));

    expect(resolved.id).toBe(0);
  });

  it("never reports a missing thread number as an unsupported event", () => {
    // Both failures throw; the exact messages above are what separate the two
    // branches. This states the confusion explicitly for the reader.
    const thrown = (): ThreadContext =>
      resolveThread(eventOf("issue_comment", { action: "created" }));

    expect(thrown).toThrowError(new Error(UNRESOLVED_THREAD_MESSAGE));
    expect(thrown).not.toThrowError("Unsupported event");
  });
});
