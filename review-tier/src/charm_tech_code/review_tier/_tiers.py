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


"""The tier rules. Data in, a decision out: no network, no clock."""

from __future__ import annotations

import collections
import dataclasses
import difflib
import fnmatch
import re
import tomllib
from typing import TYPE_CHECKING, Any

from ._config import PATH

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ._config import Config

DEPENDABOT = 'dependabot[bot]'
TEAM = 'Team PRs on low-risk paths'
DEPENDABOT_TIER = 'Dependabot bumps'
RELEASE = 'Automated release PRs'
BOT = 'prints-charming-bot updates'


@dataclasses.dataclass(frozen=True)
class Commit:
    """A commit on the PR, as the REST API attributes it."""

    sha: str
    author: str | None
    committer: str | None
    verified: bool
    message: str


@dataclasses.dataclass
class PullRequest:
    """What the rules need to know about a PR.

    `read` returns a file's text at the merge base (`'base'`) or the head
    (`'head'`), or None where the file doesn't exist.
    """

    title: str
    author: str
    branch: str
    lines_changed: int
    files: list[tuple[str, str | None]]  # (path, previous path if renamed)
    commits: list[Commit]
    labels_ever: set[str]  # Every label the PR has had, not only the current ones.
    read: Callable[[str, str], str | None]
    # Set when GitHub's list of commits or files stops short of the whole PR.
    incomplete: str | None = None

    def paths(self) -> Iterable[str]:
        """Every path the PR touches, including where a renamed file came from."""
        for path, previous in self.files:
            yield path
            if previous:
                yield previous


@dataclasses.dataclass(frozen=True)
class Decision:
    """The tier a PR is in, how many approvals that needs, and why."""

    tier: str | None
    required: int
    reason: str


def decide(pr: PullRequest, cfg: Config) -> Decision:
    """Put a PR in a tier. Only the tier the author points to is tried."""
    if cfg.label in pr.labels_ever:
        return Decision(
            None,
            2,
            f'`{cfg.label}` has been added to this PR, so it needs two approvals,'
            ' even if the label has since been removed.',
        )
    if pr.incomplete:
        return Decision(None, 2, f'{pr.incomplete}, so it needs two approvals.')
    if pr.author.lower() in cfg.team:
        name, (ok, why) = TEAM, team_tier(pr, cfg)
    elif pr.author == DEPENDABOT:
        name, (ok, why) = DEPENDABOT_TIER, dependabot_tier(pr)
    elif pr.author == cfg.release_author:
        name, (ok, why) = RELEASE, release_tier(pr, cfg)
    elif pr.author == cfg.bot_author:
        name, (ok, why) = BOT, bot_tier(pr, cfg)
    else:
        return Decision(
            None,
            2,
            f'@{pr.author} is not on the team list in `{PATH}`, and is not'
            ' Dependabot, the release workflow or the docs and pins bot.',
        )
    return Decision(name, 1, f'{name}: {why}') if ok else Decision(None, 2, f'{name}: {why}')


def matches(path: str, patterns: Iterable[str]) -> str | None:
    """The first glob that matches `path`, or None. `*` matches across `/`."""
    return next((p for p in patterns if fnmatch.fnmatchcase(path, p)), None)


def team_tier(pr: PullRequest, cfg: Config) -> tuple[bool, str]:
    """Team PRs on low-risk paths: an allow-list of paths, under a line limit."""
    if not pr.files:
        return False, 'the PR changes no files.'
    for path in pr.paths():
        if not matches(path, cfg.allow):
            return False, f'`{path}` is not on a low-risk path.'
        if excluded := matches(path, cfg.allow_except):
            return False, f'`{path}` is excluded from the low-risk paths by `{excluded}`.'
    if pr.lines_changed >= cfg.line_limit:
        return False, f'{pr.lines_changed} lines changed, and the limit is {cfg.line_limit}.'
    return True, (
        f'@{pr.author} is on the team list, every changed file ({len(pr.files)}) is on a'
        f' low-risk path, and {pr.lines_changed} lines changed (under {cfg.line_limit}).'
    )


_UPDATES = re.compile(r'^updated-dependencies:\n(.*?)^\.\.\.$', re.M | re.S)
_BUMP = re.compile(r'from v?(\d+)(?:\.(\d+))?\S* to v?(\d+)(?:\.(\d+))?')


def update_types(message: str) -> list[tuple[str, str | None]]:
    """(dependency, semver kind or None) for each update in a Dependabot commit message.

    Dependabot calls a change to the second number of a 0.x version (0.41 to
    0.42) a minor update, but on 0.x that's the number that changes when
    something breaks, so it counts as major here, as it does for a title.
    """
    out: list[tuple[str, str | None]] = []
    for block in _UPDATES.findall(message):
        for entry in re.split(r'^- ', block, flags=re.M)[1:]:
            name = re.search(r'dependency-name: (\S+)', entry)
            kind = re.search(r'^\s*update-type: version-update:semver-(\w+)\s*$', entry, re.M)
            version = re.search(r'dependency-version: v?(\S+)', entry)
            kind = kind[1] if kind else None
            if kind == 'minor' and version and version[1].startswith('0.'):
                kind = 'major'
            out.append((name[1] if name else '?', kind))
    return out


def bump_is_major(line: str) -> bool | None:
    """Whether a 'from X to Y' line crosses a major version, or a minor one on 0.x.

    None if the line doesn't say.
    """
    m = _BUMP.search(line)
    if not m:
        return None
    old_major, old_minor, new_major, new_minor = m.groups()
    return old_major != new_major or (old_major == '0' and old_minor != new_minor)


def messages_are_major(messages: list[str]) -> bool | None:
    """Whether any 'from X to Y' line in the commit messages is a major bump.

    The commit messages are signed, but the PR's title can be edited by anyone
    with write access, so only the messages are read. None if no line says.
    """
    found = [bump_is_major(line) for m in messages for line in m.splitlines()]
    found = [major for major in found if major is not None]
    return any(found) if found else None


def dependabot_tier(pr: PullRequest) -> tuple[bool, str]:
    """Dependabot bumps: only Dependabot's commits, and no semver major."""
    if not pr.commits:
        return False, 'the PR has no commits.'
    for c in pr.commits:
        # Dependabot's commits are signed and committed by GitHub. An author
        # email can be set to anything; a verified web-flow signature can't.
        if c.author != DEPENDABOT or c.committer != 'web-flow' or not c.verified:
            return False, (
                f'commit {c.sha[:7]} is by {c.author or "an unknown author"}, not a signed'
                f' {DEPENDABOT} commit, so this is no longer just a bump.'
            )
    updates = [u for c in pr.commits for u in update_types(c.message)]
    majors = [name for name, kind in updates if kind == 'major']
    if majors:
        return False, f'{", ".join(majors)} is a semver-major update (or a minor one on 0.x).'
    if updates and all(kind for _, kind in updates):
        return True, f'every update ({len(updates)}) is minor or patch, by update-type metadata.'
    major = messages_are_major([c.message for c in pr.commits])
    if major is None:
        return False, (
            'there is no update-type metadata, and the commit messages have no versions to'
            ' compare.'
        )
    if major:
        return False, (
            'there is no update-type metadata, and the commit messages have a major bump'
            ' (or a minor one on 0.x).'
        )
    return True, (
        'there is no update-type metadata, and the commit messages only have minor or patch bumps.'
    )


def changed_lines(base: str | None, head: str | None) -> list[str]:
    """Every line removed from `base` or added in `head`."""
    removed, added = _removed_added(base, head)
    return removed + added


def _removed_added(base: str | None, head: str | None) -> tuple[list[str], list[str]]:
    """The lines removed from `base`, and the lines added in `head`."""
    a, b = (base or '').splitlines(), (head or '').splitlines()
    removed: list[str] = []
    added: list[str] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op != 'equal':
            removed += a[i1:i2]
            added += b[j1:j2]
    return removed, added


def _line_keys(lines: list[str], allowed: re.Pattern[str]) -> collections.Counter[str]:
    """What each version or pin line sets: `version`, or the package (with any extras)."""
    keys: collections.Counter[str] = collections.Counter()
    for line in lines:
        m = allowed.fullmatch(line)
        assert m is not None  # _bad_line has already checked every line.
        keys['version' if m[2] else m[4] + (m[5] or '')] += 1
    return keys


def _bad_line(pr: PullRequest, path: str, pattern: re.Pattern[str]) -> str | None:
    for line in changed_lines(pr.read(path, 'base'), pr.read(path, 'head')):
        if not pattern.fullmatch(line):
            return f'`{path}` changes a line that is not allowed: `{line.strip()}`'
    return None


def release_tier(pr: PullRequest, cfg: Config) -> tuple[bool, str]:
    """Automated release PRs: release files, and only versions and our own pins in them."""
    if not matches(pr.branch, cfg.release_branches):
        return False, f'the branch `{pr.branch}` is not a release branch.'
    if extra := sorted(set(pr.paths()) - cfg.release_files):
        return False, f'`{extra[0]}` is not a release file.'
    names = '|'.join(re.escape(p) for p in sorted(cfg.release_packages))
    allowed = re.compile(
        r'\s*version(\s*:\s*str)?\s*=\s*([\'"])[^\'"]+\2\s*'
        rf'|\s*([\'"])({names})(\[[^\]]*\])?==[^\'"\s]+\3,?\s*'
    )
    for path in sorted(cfg.release_line_checked & set(pr.paths())):
        if bad := _bad_line(pr, path, allowed):
            return False, bad + '.'
        # Every version or pin removed must be put back with a new value, so a
        # release can change a pin but can't drop one or add a new one.
        removed, added = _removed_added(pr.read(path, 'base'), pr.read(path, 'head'))
        if _line_keys(removed, allowed) != _line_keys(added, allowed):
            return False, f'`{path}` adds or removes a version or pin, rather than changing one.'
    lock = cfg.release_lockfile
    if lock in set(pr.paths()):
        base, head = pr.read(lock, 'base'), pr.read(lock, 'head')
        if base is None or head is None:
            return False, f'`{lock}` was added or removed.'
        if diffs := lock_differences(base, head, cfg.release_packages):
            shown = '; '.join(diffs[:5]) + ('; ...' if len(diffs) > 5 else '')
            return False, f'`{lock}` changes more than our own versions: {shown}.'
    return True, (
        f'only release files changed, and the only changes to versions, pins and `{lock}`'
        f' are to {", ".join(sorted(cfg.release_packages))}.'
    )


def bot_tier(pr: PullRequest, cfg: Config) -> tuple[bool, str]:
    """prints-charming-bot updates: a fixed branch, a fixed file set, and a line check."""
    branch = cfg.bot_branches.get(pr.branch)
    if branch is None:
        return False, f'the branch `{pr.branch}` is not one of the bot branches.'
    if extra := sorted(set(pr.paths()) - branch.files):
        return False, f'`{extra[0]}` is not one of the files `{pr.branch}` may change.'
    if branch.lines:
        pattern = re.compile(branch.lines)
        for path in sorted(set(pr.paths())):
            if bad := _bad_line(pr, path, pattern):
                return False, bad + '.'
    return True, f'`{pr.branch}` changed only the files and lines it is allowed to.'


def _strip(node: Any, own: frozenset[str]) -> Any:
    """Drop our own packages' versions, and the specifiers of requirements on them."""
    if isinstance(node, dict):
        ours = node.get('name') in own
        return {
            k: _strip(v, own)
            for k, v in node.items()
            if not (ours and k in ('version', 'specifier'))
        }
    if isinstance(node, list):
        return [_strip(v, own) for v in node]
    return node


def _key(item: Any) -> str | None:
    if isinstance(item, dict) and 'name' in item:
        return ' '.join(str(item[k]) for k in ('name', 'version') if k in item)
    return None


def _diff(a: Any, b: Any, path: str) -> list[str]:
    if a == b:
        return []
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(a.keys() | b.keys()):
            if k not in a:
                out.append(f'{path}{k} added')
            elif k not in b:
                out.append(f'{path}{k} removed')
            else:
                out += _diff(a[k], b[k], f'{path}{k}.')
        return out
    if isinstance(a, list) and isinstance(b, list):
        # A list of plain strings (`provides-extras`) is a set: uv versions
        # differ in the order they write it, and the order means nothing.
        if all(isinstance(x, str) for x in a + b) and sorted(a) == sorted(b):
            return []
        ka, kb = [_key(x) for x in a], [_key(x) for x in b]
        # A list of named entries (packages, dependencies) is compared by name,
        # so the message says which one changed rather than that the list did.
        if None not in ka + kb and len(set(ka)) == len(ka) and len(set(kb)) == len(kb):
            da, db = dict(zip(ka, a, strict=True)), dict(zip(kb, b, strict=True))
            where = path[:-1]
            return [
                *(f'{where}: {k} added' for k in kb if k not in da),
                *(f'{where}: {k} removed' for k in ka if k not in db),
                *(d for k in ka if k in db for d in _diff(da[k], db[k], f'{where}[{k}].')),
            ]
    return [f'{path[:-1]} changed']


def lock_differences(base: str, head: str, own: frozenset[str]) -> list[str]:
    """How two `uv.lock` files differ, other than in our own packages' versions and pins.

    Both are compared as TOML, not as text, so ordering and formatting can't hide
    anything and can't fail the check, and a list of plain strings is compared as
    a set. A dependency added, removed, re-pinned or
    given a new marker, or a change to the lock's own header, is a difference.
    """
    return _diff(_strip(tomllib.loads(base), own), _strip(tomllib.loads(head), own), '')


def approvers(reviews: list[dict[str, Any]], author: str, reviewers: frozenset[str]) -> list[str]:
    """The reviewers whose latest decision on the PR is still an approval.

    `reviews` is the REST API's list, which is oldest first. A comment doesn't
    change a reviewer's decision; requesting changes, or having the approval
    dismissed (by hand, or by a push), takes it away. Only the logins in
    `reviewers` (lowercase) count, as anyone can approve a PR on a public
    repository. Bots and the author don't count, and each reviewer counts once.
    """
    latest: dict[str, str] = {}
    for r in reviews:
        user = r.get('user') or {}
        login = user.get('login')
        if (
            not login
            or login == author
            or user.get('type') == 'Bot'
            or login.lower() not in reviewers
        ):
            continue
        if r.get('state') in ('APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'):
            latest[login] = r['state']
    return sorted(login for login, state in latest.items() if state == 'APPROVED')
