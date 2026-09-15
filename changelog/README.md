# changelog

Turns a range of commits into our changelog format.

The Charm Tech repositories have different release processes, but aim for a consistent changelog style. The formatting and the version arithmetic are centralised here, the file rewriting and the GitHub calls are in each repository.

## Using it

```python
import datetime
import subprocess
from charm_tech_code.changelog import (
    GIT_LOG_FORMAT,
    format_changes,
    format_release_notes,
    infer_bump_size,
    next_version,
    parse_git_log,
)

log = subprocess.run(
    ['git', 'log', '--reverse', '--no-merges', f'--format={GIT_LOG_FORMAT}', '3.8.1..3.8.2'],
    capture_output=True,
    text=True,
    check=True,
).stdout
categories = parse_git_log(log, team=MAINTAINERS, repo='canonical/operator')
notes = format_release_notes(categories, None, repo='canonical/operator')
version = next_version(previous='3.8.1', size=infer_bump_size(categories))
entry = format_changes(categories, version, datetime.date.today())
```

Running `git log` is the caller's job, as is getting hold of the date: nothing in the library touches the network, git, the filesystem or the clock. That is what lets the tests pin the real behaviour rather than approximate it.

### The pull-request number, and the link

A change carries the *number*, taken from the `(#N)` a squash merge appends to the subject, and never a URL. `format_changes` only ever wanted the number, and `format_release_notes` builds the link back up from the number and the `repo` you give it - a string operation, so the no-I/O rule holds.

A commit with no `(#N)` - one pushed straight to the branch - carries `None`, and renders with no reference at all rather than with a `(#?)` standing in for one. It is a real change; what it has not got is a pull request to point anyone at.

### Credit

A contributor from outside the team maintaining the repository is named in the bullet: `* Fix typos in code snippets by @MattiaSarti (#1750)`, which is what operator's own `CHANGES.md` has always done by hand. A member of that team is not - a maintainer is not a guest, and a changelog whose every line ends in the same three handles has stopped carrying information.

Pass the team as `team=`, a collection of email addresses and/or GitHub handles. It is a parameter rather than a constant because it drifts, and it differs per repository. **An empty team credits everyone**, which is the right way for this to fail: over-crediting is visible in the draft release and takes one edit, while crediting nobody is invisible until a contributor notices.

Two things about who is outside:

* **"Outside the team" is not "outside Canonical".** Someone from another Canonical team has an `@canonical.com` address and every bit as much claim to the credit.
* **A handle is only sometimes recoverable.** `46688206+Ali-932@users.noreply.github.com` gives `@Ali-932`, which is GitHub's default for an account with a private email and so the usual case for a drive-by contributor. Where there is no handle in the log, the person is credited by name, because dropping them and rendering a broken `@` are both worse.

### Reverts

Handled explicitly, on the git-log path:

* **A revert of something in the same range cancels with it**, and neither appears. A change that landed and was taken back out before anything shipped did not happen as far as a reader is concerned.
* **A revert of something already released is called out**, under its own `Reverted` heading rather than filed under the type it undoes - the reader wants to see that something was withdrawn, not a fix that looks new. It counts at least as a patch, and a revert of a released *feature* is routed to `Breaking Changes`, because taking away behaviour people may be relying on is a breaking change whatever the revert commit's type says.

The key is the pull-request number in `Reverts owner/repo#N`, not a SHA. Under squash merging the reverted commit's SHA on the default branch bears no relation to anything a contributor would cite.

## From a workflow step

The console script is the same thing for a caller that can't `import`. It reads the range on stdin and prints one answer:

```shell
git log --reverse --no-merges --format="$(changelog git-log-format)" "$LAST_TAG..$BRANCH" > log.txt
SIZE=$(changelog bump-size --team "$TEAM" < log.txt)
VERSION=$(changelog next-version --previous "$LAST_TAG" --team "$TEAM" < log.txt)
changelog release-notes --repo "$REPO" --team "$TEAM" \
    --compare-url "https://github.com/$REPO/compare/$LAST_TAG...$VERSION" < log.txt > release-notes.md
changelog changes-entry --tag "$VERSION" --team "$TEAM" < log.txt > changes-entry.md
```

That shape comes from how an Actions step consumes a result. A `$GITHUB_OUTPUT` line takes a scalar comfortably and a multi-line document only through a heredoc delimiter the document itself must not contain, so the two commands that produce Markdown print it on stdout for the step to redirect into a file, and the two that produce a scalar print a single bare word, with no label and no JSON to unwrap. Nothing here writes to `$GITHUB_OUTPUT` itself, which keeps the script useful outside Actions.

Four invocations re-parse the same text four times. That costs nothing worth counting, and it is the reason each step's output needs no reshaping.

`git-log-format` is the fifth and the odd one out: it reads nothing, and prints the `--format` string the others expect. Copying that string into the workflow instead would work until someone dropped a separator out of it, and a log that does not parse yields an empty changelog rather than an error.

`--compare-url` is there because a git log does not carry a compare link and the tags at either end of the range are the workflow's to know. You pass the link; the `**Full Changelog**:` prefix is the package's, so that notes rendered here read the same as notes rendered by GitHub. Leave it off for no closing line.

`--date` defaults to today (UTC), and `_cli` is the only module in the package that reads the clock. The library stays clock-free, and a fixture in the test suite fails the whole run if that stops being true.

Run it from a workflow the way `ai-failure-notifier` is run, pinned to a commit:

```shell
uvx --from "git+https://github.com/canonical/charm-tech-code@<40-char-sha>#subdirectory=changelog" changelog bump-size < log.txt
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
* `breaking` is a category but not a type. A `!` after the real type (`feat!:`) moves an entry into it, keeping its real type as a prefix, and it renders first with a sentence asking the reader to review carefully. A revert of a released `feat` lands there too, for the reason in "Reverts" above. A `!` should be a major version bump, but if it's appearing here then we have decided to cheat the semver rules and allow a breaking change in a minor release. This should be rare. We will have carefully checked the impact before this decision, but want to make sure the change is particularly noticeable in the changelog.

## Developing

```shell
uv sync --group unit
uv run pytest
```
