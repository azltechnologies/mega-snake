The release type decides how visible the release is once published. A **pre-release** is announced
as unfinished, so it never becomes the version GitHub offers by default — the usual choice for a
build meant for testing. A **latest** release is the opposite: it takes over the `latest` pointer
and becomes what users land on, which is why the command asks for confirmation first. A plain
**release** publishes without touching that pointer, so an older version stays the recommended one;
if GitHub moves it anyway, the command puts it back where it was.

Publishing is delegated to the [`gh`](https://cli.github.com) CLI, which means it reuses the GitHub
authentication you already have — there is no token to configure here.

## Notes

Light-weight: it runs from anywhere, no workspace required. When `branch` is omitted the release is
cut from the current branch.
