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
counter that grows so the same version can be built repeatedly. It is **rejected for the `l` type**:
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

The new tag is always derived from the release GitHub currently marks as `latest`, which is never a
pre-release. A release tagged by hand in the GitHub UI *can* hold that mark with any tag text, so the
command refuses to continue when that tag is not a `vX.Y.Z` version: there is nothing to increment.
Publish a version-tagged release first, or create that one with `gh release create`. It also refuses when the derived
tag already exists, which means the repository holds a tag without a matching release.
