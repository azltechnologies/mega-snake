The release type decides how visible the release is once published. A **pre-release** is announced
as unfinished, so it never becomes the version GitHub offers by default — the usual choice for a
build meant for testing. A **latest** release is the opposite: it takes over the `latest` pointer
and becomes what users land on, which is why the command asks for confirmation first. A plain
**release** publishes without touching that pointer, so an older version stays the recommended one;
if GitHub moves it anyway, the command puts it back where it was.

The new tag is **derived, never typed**: the command reads the latest release, increments one
component of its version, and uses the result. That is what keeps the sequence continuous — the next
release always follows the one actually published, so two people cutting releases from different
checkouts cannot invent conflicting numbers.

`--version-part` chooses which component moves, and everything to its right restarts:

| From `v1.2.3` | Result | When to use it |
|---|---|---|
| `--version-part patch` *(default)* | `v1.2.4` | Fixes and changes that keep the same behaviour |
| `--version-part minor` | `v1.3.0` | New functionality that stays backwards compatible |
| `--version-part major` | `v2.0.0` | Breaking changes |

Resetting is what keeps the order monotonic: a minor bump that produced `v1.3.3` would sit above the
patches that follow it.

`--tag-suffix` marks the result as a pre-release build of that version — `v1.2.4-beta.0` — with a
counter that grows so the same version can be built repeatedly. The base version is derived the same
way as for a plain release, so a pre-release always announces a version that has **not** shipped yet:
`v1.2.5-beta.0` precedes `v1.2.5`, never trails `v1.2.4`. Pre-release tags do not raise the ceiling
either, so one beta cannot push the next release past it. It is **rejected for the `l` type**:
GitHub only grants the `latest` pointer to a plain version, so asking for a suffixed latest release
is something the platform cannot honour.

Publishing is delegated to the [`gh`](https://cli.github.com) CLI, which means it reuses the GitHub
authentication you already have — there is no token to configure here.

## Examples

```bash
# A patch release from the current branch
mgsnake cr l

# A minor release with notes, cut from a specific branch
mgsnake cr l "Adds the man command" release/2.1 --version-part minor

# A prerelease build of the next patch: v1.2.4-beta.0, then -beta.1, ...
mgsnake cr p --tag-suffix beta

# A prerelease, which never takes over the latest pointer
mgsnake cr p
```

## Notes

Light-weight: it runs from anywhere, no workspace required. When `branch` is omitted the release is
cut from the current branch.

The new tag is derived from the **highest `vX.Y.Z` tag in the repository**, not from the `latest`
pointer alone. Prereleases and `r` releases publish tags without moving that pointer, so it can sit
below tags that already exist; taking the maximum on every derivation is what makes the guarantee
hold unconditionally — a new tag can never land below one that was already published. The `latest`
release still decides whether the version is usable at all (see the note below).

## Tag patterns

The tag format is **not** hard-coded. A pattern describes the tags this project already uses, with
`$1`, `$2` and `$3` standing for the major, minor and patch numbers; everything else is literal, and
`$$` is a literal `$`. The same string parses the current tag and renders the next one, so the two
can never disagree.

| Pattern | Latest tag | Next patch |
|---|---|---|
| `v$1.$2.$3` *(default)* | `v1.2.3` | `v1.2.4` |
| `$1.$2.$3` | `1.2.3` | `1.2.4` |
| `rel-$1_$2_$3` | `rel-1_2_3` | `rel-1_2_4` |

Set it per invocation with `--tag-pattern`, or per project with the `release_tag_pattern` property.
All three placeholders are required, since `--version-part` names exactly those three components.

The pattern must match the tag of the latest release, and the command stops when it does not — a
pattern that describes nothing in the repository would otherwise fail much later, with nothing
pointing at it as the cause. Only tags the pattern recognises count towards the next version, so tags
left over from a different scheme never raise the ceiling.
