# changelog

Turns GitHub's generated release notes into our changelog format.

The Charm Tech repositories have different release processes, but aim for a consistent changelog style. The formatting and the version arithmetic are centralised here, the file rewriting and the GitHub calls are in each repository.

## Using it

```python
import datetime
from charm_tech_code.changelog import (
    format_changes,
    format_release_notes,
    infer_bump_size,
    next_version,
    parse_release_notes,
)

categories, full_changelog = parse_release_notes(notes_text)
notes = format_release_notes(categories, full_changelog)
version = next_version('3.8.1', infer_bump_size(categories))
entry = format_changes(categories, version, datetime.date.today())
```

`notes_text` is GitHub's *generated* release-notes text, not a `git log`. GitHub builds it from the titles of the pull requests merged in the range, which is why the conventional-commit types come off PR titles. A release already has that text in its body; a workflow running before any release exists can ask for a preview of it with `POST /repos/{owner}/{repo}/releases/generate-notes`. Either way, getting hold of it is the caller's job: nothing in the library touches the network, git, the filesystem or the clock, and `format_changes` takes the date as an argument for the same reason.

## From a workflow step

The console script is the same thing for a caller that can't `import`. It reads the notes on stdin and prints one answer:

```shell
gh api "repos/$REPO/releases/generate-notes" -f tag_name="$TAG" -f target_commitish="$BRANCH" --jq .body > notes.md
SIZE=$(changelog bump-size < notes.md)
VERSION=$(changelog next-version --previous "$LAST_TAG" < notes.md)
changelog release-notes < notes.md > release-notes.md
changelog changes-entry --tag "$VERSION" < notes.md > changes-entry.md
```

That shape comes from how an Actions step consumes a result. A `$GITHUB_OUTPUT` line takes a scalar comfortably and a multi-line document only through a heredoc delimiter the document itself must not contain, so the two commands that produce Markdown print it on stdout for the step to redirect into a file, and the two that produce a scalar print a single bare word, with no label and no JSON to unwrap. Nothing here writes to `$GITHUB_OUTPUT` itself, which keeps the script useful outside Actions.

Four invocations re-parse the same text four times. That costs nothing worth counting, and it is the reason each step's output needs no reshaping.

`--date` defaults to today (UTC), and `_cli` is the only module in the package that reads the clock. The library stays clock-free, and a fixture in the test suite fails the whole run if that stops being true.

Run it from a workflow the way `ai-failure-notifier` is run, pinned to a commit:

```shell
uvx --from "git+https://github.com/canonical/charm-tech-code@<40-char-sha>#subdirectory=changelog" changelog bump-size < notes.md
```

## Versions

`infer_bump_size` answers "how big a release is this range", and `next_version` applies that answer to a plain `X.Y.Z`. The rule is that a `feat` in the range means minor and anything else means patch, with two things worth saying out loud:

* **A breaking change counts as a feature.** A `!` moves an entry out of its real type and into `breaking`, so a range whose only feature is a `feat!` has an empty `feat` list, and a rule that read `feat` alone would call it a patch. A `!` doesn't infer a *major* bump, for the reason in "The format" below, but a breaking change riding in a patch release isn't the bend of the rules anyone agreed to. operator's 3.8.0 shipped a `refactor!` in a minor release, which is the case this matches.
* **A major bump is never inferred.** Nor is a pre-release, and `next_version` raises rather than guess at anything that isn't a plain `X.Y.Z`: `3.9.0.dev0` is the one to watch, since that's what sits in the version file between releases and it's a guess made by the last post-release bump rather than a version anyone shipped. A release that isn't an ordinary next one is a deliberate act, and the workflow's explicit version input is how to say so.

Where the line falls: the package says what size the range is and does the semver arithmetic, and the repository decides what to count from, whether a `.dev0` goes on the end afterwards, and what any of it implies for the other packages it ships. A `minor` on a branch where a feature has no business appearing, such as operator's `2.23-maintenance`, is an error rather than a patch, but it's the repository that knows which branches those are, so that check belongs there too.

## The format

`format_release_notes` produces the body of a GitHub release, and `format_changes` produces one `CHANGES.md` entry:

```markdown
# 3.8.2 - 31 August 2026

## Fixes

* Compare full event paths when skipping duplicate notices (#2684)
```

Neither shape is injectable, and neither is the map of commit type to heading. The format is common across our repositories and the set of types is enforced by a shared PR-title check, so there is no second format for an adopting repository to supply, and a template system here would exist for a caller that doesn't.

Two things about that map are worth knowing before you decide it's wrong:

* `chore` is a type but not a category, so `chore` commits are deliberately dropped. Dependency bumps, charm-pin updates and the release's own version-bump commit are all `chore`, and these sorts of changes are not interesting to our users, and they are available via `git log` if anyone does want them.
* `breaking` is a category but not a type. A `!` after the real type (`feat!:`) moves an entry into it, keeping its real type as a prefix, and it renders first with a sentence asking the reader to review carefully. A `!` should be a major version bump, but if it's appearing here then we have decided to cheat the semver rules and allow a breaking change in a minor release. This should be rare. We will have carefully checked the impact before this decision, but want to make sure the change is particularly noticeable in the changelog.

## Developing

```shell
uv sync --group unit
uv run pytest
```
