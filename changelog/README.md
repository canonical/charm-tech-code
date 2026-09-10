# changelog

Turns GitHub's generated release notes into our changelog format.

The Charm Tech repositories have different release processes, but aim for a consistent changelog style. The formatting and the version arithmetic are centralised here, the file rewriting and the GitHub calls are in each repository.

## Using it

```python
import datetime
from charm_tech_code.changelog import format_changes, format_release_notes, parse_release_notes

categories, full_changelog = parse_release_notes(notes_text)
notes = format_release_notes(categories, full_changelog)
entry = format_changes(categories, '3.8.2', datetime.date.today())
```

`notes_text` is GitHub's *generated* release-notes text, not a `git log`. GitHub builds it from the titles of the pull requests merged in the range, which is why the conventional-commit types come off PR titles. A release already has that text in its body; a workflow running before any release exists can ask for a preview of it with `POST /repos/{owner}/{repo}/releases/generate-notes`. Either way, getting hold of it is the caller's job: nothing here touches the network, git, the filesystem or the clock, and `format_changes` takes the date as an argument for the same reason.

There's no console script, because what a command line would need to look like depends on the workflow calling it, and that workflow hasn't been written yet.

## The format

`format_release_notes` produces the body of a GitHub release, and `format_changes` produces one `CHANGES.md` entry:

```markdown
# 3.8.2 - 31 August 2026

## Fixes

* Compare full event paths when skipping duplicate notices (#2684)
```

Neither shape is injectable, and neither is the map of commit type to heading. The format is common across our repositories and the set of types is enforced by a shared PR-title check, so there is no second format for an adopting repository to supply, and a template system here would exist for a caller that doesn't.

Two things about that map are worth knowing before you decide it's wrong:

* `chore` is a type but not a category, so `chore` commits are dropped. That's deliberate. Dependency bumps, charm-pin updates and the release's own version-bump commit are all `chore`, and in a typical operator release they're a third to a half of the commits in the range.
* `breaking` is a category but not a type. A `!` after the real type (`feat!:`) moves an entry into it, keeping its real type as a prefix, and it renders first with a sentence asking the reader to review carefully. A `!` deliberately doesn't infer a major version bump, so that calling-out is the only thing marking it.

## Developing

```shell
uv sync --group unit
uv run pytest
```
