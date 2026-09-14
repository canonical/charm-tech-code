# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Reading a range of changes out of text, into categories.

Two doors in, one room behind them. `parse_git_log` is the one to use: the
conventional-commit convention governs *commits*, so the commits are what a
changelog should be read off. `parse_release_notes` reads GitHub's generated
notes instead, which describe the same pull requests by their *titles*; it
is kept because a caller that already has a release body in hand should not
have to go and fetch a git log to use it.

Where they differ is worth knowing before picking one:

* A pull-request title is written once, when the pull request is opened, and
  is not what the conventional-commit rule is about. The squashed subject is
  what lands on the branch and what everything else in the repository reads.
  When the two disagree, the git log is right.
* A revert can only be resolved from a git log. Working out whether a revert
  cancels something in the same range means reading the revert commit's
  *body*, and GitHub's generated notes are one line per pull request with no
  body anywhere in them.
* The notes carry a handle for every author; the git log carries a name and
  an email, from which a handle is sometimes recoverable and sometimes not.
  See `_authors`.
* The notes end with a compare link and a git log has no equivalent, so
  `parse_git_log` has nothing to return in its place.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import NamedTuple

from ._authors import credit_for, credit_for_handle
from ._constants import (
    BREAKING,
    CATEGORIES,
    CHANGE_LINE_REGEX,
    COMMIT_SUBJECT_REGEX,
    FULL_CHANGELOG_PREFIX,
    GIT_LOG_FIELD_SEPARATOR,
    GIT_LOG_RECORD_SEPARATOR,
    NEW_CONTRIBUTORS_REGEX,
    PR_LINK_REGEX,
    PR_SUFFIX_REGEX,
    REVERT,
    REVERT_OF_BREAKING_TYPES,
    REVERTS_REGEX,
)
from ._models import Change


def _empty_categories() -> dict[str, list[Change]]:
    """Every category, in render order, whether or not the range filled it.

    Callers index `categories['breaking']` and iterate the dict for the
    order, so the shape must not depend on what happened to be released.
    """
    return {category: [] for category in CATEGORIES}


def _capitalise(summary: str) -> str:
    """Sentence-case a summary without disturbing what it starts with.

    Conventional-commit summaries are lower case after the type and
    changelog bullets are sentence case, but a summary starting with a
    backtick or a quotation mark must come through untouched.
    """
    return summary[0].upper() + summary[1:] if summary else summary


def parse_release_notes(
    release_notes: str, *, team: Collection[str] = ()
) -> tuple[dict[str, list[Change]], str | None]:
    """Parse GitHub's generated release notes into categories.

    The input is GitHub's *generated* release-notes text, not a ``git log``.
    GitHub builds it from the titles of the pull requests merged in the
    range, one ``* type!: summary by @user in <url>`` bullet each, which is
    why this reads conventional-commit types off pull-request titles rather
    than off commit subjects. `parse_git_log` reads the commits, and is the
    one to prefer for a new caller; this is here for a caller that has the
    notes text already. How it obtained that text is its own problem: a
    release has it in its body, and a workflow running before any release
    exists can ask GitHub for a preview of it. Nothing here does I/O.

    The "New Contributors" section is removed. Bullets whose type is not a
    changelog category -- `chore`, most of all -- are dropped; see
    ``_constants.CATEGORIES`` for why that is deliberate. The full-changelog
    line is returned separately rather than categorised.

    Reverts are *not* resolved here, and cannot be: see this module's
    docstring. A revert in this range appears under `Reverted` whether or
    not the thing it reverts is also in the range.

    Args:
        release_notes: The generated notes text.
        team: Authors not to credit, as emails and/or handles. Only handles
            can match anything here, since a handle is all the notes carry.
            The default credits everyone; see `_authors`.

    Returns:
        A tuple containing:
        - A dict of category to `Change` list. Every category is present,
          even when empty, in the order they are rendered in.
        - The full changelog line if present, or ``None`` if not found.
    """
    release_notes = NEW_CONTRIBUTORS_REGEX.sub(r'\2', release_notes)
    categories = _empty_categories()
    full_changelog_line = None

    for line in release_notes.splitlines():
        if match := CHANGE_LINE_REGEX.match(line.strip()):
            category = match.group('category').strip()
            if category not in categories:
                continue
            description = _capitalise(match.group('summary').strip())
            link_match = PR_LINK_REGEX.match(match.group('pr').strip())
            pr_number = int(link_match.group(1)) if link_match else None
            credit = credit_for_handle(match.group('author'), team)
            if match.group('breaking') == '!':
                categories[BREAKING].append(
                    Change(f'{category.capitalize()}: {description}', pr_number, credit)
                )
            else:
                categories[category].append(Change(description, pr_number, credit))

        elif line.startswith(FULL_CHANGELOG_PREFIX):
            full_changelog_line = line

    return categories, full_changelog_line


class _Commit(NamedTuple):
    """One record of a `GIT_LOG_FORMAT` log, taken apart."""

    category: str
    breaking: bool
    description: str
    pr_number: int | None
    credit: str | None
    #: The pull request this commit reverts, where it says so in its body.
    reverts: int | None
    #: The conventional-commit type of the thing being reverted, read out of
    #: the quoted subject a revert carries: `revert: "feat: ..."` is `feat`.
    reverted_type: str | None
    reverted_type_is_breaking: bool


def _parse_reverts(body: str, repo: str | None) -> int | None:
    """The pull-request number a revert commit's body names, if any.

    A ``Reverts other/repo#5`` naming a different repository is not this
    range's #5, and cancelling against it would drop the wrong pair, so it
    is ignored when the caller has said which repository this log is from.
    With no `repo` to check against there is nothing to compare, and the
    reference is taken at face value.
    """
    match = REVERTS_REGEX.search(body)
    if not match:
        return None
    named_repo = match.group('repo')
    if repo is not None and named_repo is not None and named_repo.casefold() != repo.casefold():
        return None
    return int(match.group('number'))


def _parse_commit(record: str, team: Collection[str], repo: str | None) -> _Commit | None:
    """One `GIT_LOG_FORMAT` record, or `None` if it is not a change.

    A subject that is not a conventional-commit one -- a merge commit, or
    anything from before the convention was adopted -- is not a changelog
    entry and is dropped here, the same way the notes parser drops a line
    that is not a bullet.
    """
    name, _, rest = record.partition(GIT_LOG_FIELD_SEPARATOR)
    email, _, rest = rest.partition(GIT_LOG_FIELD_SEPARATOR)
    subject, _, body = rest.partition(GIT_LOG_FIELD_SEPARATOR)

    subject = subject.strip()
    pr_number = None
    if suffix := PR_SUFFIX_REGEX.search(subject):
        pr_number = int(suffix.group(1))
        subject = subject[: suffix.start()]

    match = COMMIT_SUBJECT_REGEX.match(subject)
    if not match:
        return None

    summary = match.group('summary').strip()
    reverted_type = None
    reverted_type_is_breaking = False
    if match.group('category').casefold() == REVERT:
        # `revert: "feat: add the thing"` -- the quoted subject is the one
        # being undone, and its type says how much undoing it matters. The
        # quotes are what GitHub's Revert button writes, but a hand-written
        # revert often leaves them off, so both are read.
        inner = COMMIT_SUBJECT_REGEX.match(summary.strip('"').strip())
        if inner:
            reverted_type = inner.group('category').casefold()
            reverted_type_is_breaking = inner.group('breaking') == '!'

    return _Commit(
        category=match.group('category').casefold(),
        breaking=match.group('breaking') == '!',
        description=_capitalise(summary),
        pr_number=pr_number,
        credit=credit_for(name, email, team),
        reverts=_parse_reverts(body, repo),
        reverted_type=reverted_type,
        reverted_type_is_breaking=reverted_type_is_breaking,
    )


def _cancelled(commits: list[_Commit]) -> set[int]:
    """The commits that a revert in the same range takes back out of it.

    A change that landed and was undone before anything shipped did not
    happen as far as a reader is concerned, so neither half appears: not the
    change, and not the revert of it either. Listing both would be accurate
    and useless, and listing the revert alone would describe the removal of
    something the changelog never said had arrived.

    Identity is the pull-request number, because that is what a revert body
    names and, under squash merging, the only stable thing it could name.

    Returns:
        The indices into `commits` to leave out.
    """
    numbers = {commit.pr_number: index for index, commit in enumerate(commits) if commit.pr_number}
    cancelled: set[int] = set()
    for index, commit in enumerate(commits):
        if commit.reverts is not None and commit.reverts in numbers:
            cancelled.add(index)
            cancelled.add(numbers[commit.reverts])
    return cancelled


def parse_git_log(
    log_text: str, *, team: Collection[str] = (), repo: str | None = None
) -> dict[str, list[Change]]:
    """Parse a range of commits into categories.

    This is the input to prefer. The conventional-commit convention is about
    commit subjects, `canonical/operator` squash-merges so that every subject
    on a release branch is `type: summary (#N)`, and reading the subjects is
    therefore reading the thing the convention actually governs. It also
    needs nothing from GitHub: the pull-request number comes out of the
    `(#N)` suffix, and the link a release body wants is built back up from
    that number and `repo` when it is rendered.

    `log_text` is the output of ``git log`` with ``--format=GIT_LOG_FORMAT``,
    oldest first. Getting it is the caller's job, exactly as getting the
    notes text is: nothing here runs git, or anything else.

    Three things happen that the notes path cannot do:

    * **Reverts cancel.** A revert whose pull request is also in this range
      removes both itself and what it reverted. See `_cancelled`.
    * **A revert of something already released is called out.** It keeps its
      own `Reverted` heading rather than being filed under the type it
      undoes, so that it reads as a removal and not as a new fix. A revert of
      a released feature is a withdrawal of behaviour, so it goes further and
      is routed to `breaking`; see `REVERT_OF_BREAKING_TYPES`.
    * **A commit with no `(#N)` keeps a `None`**, rather than a placeholder,
      so that a change pushed straight to the branch is visible as one.

    Args:
        log_text: `git log` output in `GIT_LOG_FORMAT`.
        team: Authors not to credit, as emails and/or handles. The default
            credits everyone; see `_authors`.
        repo: The `owner/name` this log came from, used only to ignore a
            `Reverts` line that names a different repository.

    Returns:
        A dict of category to `Change` list, in the order they are rendered
        in, with every category present even when empty. There is no second
        return value: a git log carries no compare link for the formatter to
        pass through, and inventing one would mean knowing the tags at both
        ends, which is the caller's business.
    """
    records = log_text.split(GIT_LOG_RECORD_SEPARATOR)
    commits = [
        commit
        for commit in (_parse_commit(record, team, repo) for record in records if record.strip())
        if commit is not None
    ]

    categories = _empty_categories()
    cancelled = _cancelled(commits)
    for index, commit in enumerate(commits):
        if index in cancelled or commit.category not in categories:
            continue
        change = Change(commit.description, commit.pr_number, commit.credit)
        breaking = commit.breaking or (
            commit.category == REVERT
            and (
                commit.reverted_type in REVERT_OF_BREAKING_TYPES
                or commit.reverted_type_is_breaking
            )
        )
        if breaking:
            categories[BREAKING].append(
                change._replace(
                    description=f'{commit.category.capitalize()}: {change.description}'
                )
            )
        else:
            categories[commit.category].append(change)

    return categories
