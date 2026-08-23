/**
 * Tests for the pure event-to-thread resolution.
 *
 * The resolver's contract is a closed set of event/action pairs, so the suite
 * walks that whole set rather than sampling one case, and asserts the entire
 * returned object instead of a single field. Every rejection is asserted with
 * an exact message: the two failure branches differ only in what they say, and
 * a substring assertion would not tell them apart.
 */

import { afterEach, describe, expect, it } from "vitest";
import { Context } from "@actions/github/lib/context";

import { resolveThread, ThreadEvent, UNRESOLVED_THREAD_MESSAGE } from "../../domain/thread-resolver";
import { ThreadContext } from "../../models/thread-context";
import { eventOf, OTHER_REPOSITORY, REPOSITORY, threadOf } from "../helpers";

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
      const expected: ThreadContext = threadOf(expectedType, expectedId);

      expect(resolveThread(eventOf(eventName, payload)), `wrong thread for ${name}`).toEqual(expected);
    },
  );

  it.each(SUPPORTED)(
    "returns the repository it was given for $name, never one of its own",
    ({ name, eventName, payload, expectedId }) => {
      // Resolved with a repository no other fixture uses, so a hardcoded or
      // default-valued return cannot satisfy this.
      const resolved = resolveThread(eventOf(eventName, payload, OTHER_REPOSITORY));

      expect(resolved.issue, `wrong issue for ${name}`).toEqual({ ...OTHER_REPOSITORY, id: expectedId });
      expect(resolved.issue, `${name} fell back to the default repository`).not.toEqual({
        ...REPOSITORY,
        id: expectedId,
      });
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

  it("rejects an unsupported event before it ever reads the issue reference", () => {
    // `context.issue` is a getter, and it reaches `context.repo`, which throws
    // when GITHUB_REPOSITORY is unset. Destructuring it above the switch would
    // replace the real diagnosis with that one, on an event we never supported.
    const event = {
      eventName: "push",
      payload: { action: "created" },
      get issue(): never {
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

    expect(resolved.issue.id).toBe(0);
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

/**
 * The resolver no longer reads the thread number itself: it takes whatever
 * `context.issue` derived. That makes the getter's behaviour part of this
 * module's contract, and `eventOf` a *stub of the SDK* rather than a plain
 * fixture - so the stub is compared against the real class here. Without this,
 * a change of precedence upstream would silently retarget every session log.
 */
describe("context.issue", () => {
  const previousRepository = process.env.GITHUB_REPOSITORY;
  const previousEventPath = process.env.GITHUB_EVENT_PATH;

  afterEach(() => {
    process.env.GITHUB_REPOSITORY = previousRepository;
    process.env.GITHUB_EVENT_PATH = previousEventPath;
  });

  /**
   * Read `issue` off a real `Context` carrying `payload`.
   *
   * @param payload - The webhook payload the runner would deliver.
   * @returns Whatever the SDK getter derives from it.
   */
  function realIssue(payload: Record<string, unknown>): Context["issue"] {
    process.env.GITHUB_REPOSITORY = `${REPOSITORY.owner}/${REPOSITORY.repo}`;
    delete process.env.GITHUB_EVENT_PATH;

    const context = new Context();
    context.payload = payload as Context["payload"];
    return context.issue;
  }

  it.each([
    { name: "an issue payload", payload: { issue: { number: 42 } }, expectedId: 42 },
    { name: "a pull request payload", payload: { pull_request: { number: 7 } }, expectedId: 7 },
    {
      name: "a payload carrying both keys",
      payload: { issue: { number: 42 }, pull_request: { number: 7 } },
      expectedId: 42,
    },
    { name: "a bare payload", payload: { number: 3 }, expectedId: 3 },
    { name: "a payload with no number anywhere", payload: {}, expectedId: undefined },
  ])("derives $name the same way eventOf does", ({ name, payload, expectedId }) => {
    const real = realIssue(payload);

    expect(real.number, `the SDK changed how it derives the number for ${name}`).toBe(expectedId);
    expect(eventOf("issue_comment", payload).issue, `eventOf drifted for ${name}`).toEqual(real);
  });

  it("carries the repository, so the resolver never has to read it separately", () => {
    expect(realIssue({ issue: { number: 42 } })).toEqual({ ...REPOSITORY, number: 42 });
  });
});
