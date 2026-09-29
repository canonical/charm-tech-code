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


"""Decide what a push, or a published release, means for a branch's version.

Two moments in a release pipeline need a version decision that is the same in
every repository, whichever file the version lives in:

- **A push lands on a release branch.** Is it a release? `detect_release`.
- **A release is published.** Which branch was it cut from, and which
  development version does that branch go to now? `resolve_branch` and
  `next_dev_version`.

These take and return version strings. Reading the version out of a file,
and writing the new one back, is the repository's business.
"""

from __future__ import annotations

from collections.abc import Sequence

from ._constants import MAINTENANCE_BRANCH_SUFFIX, PIPELINE_VERSION_REGEX


def detect_release(before: str | None, after: str) -> tuple[str | None, str]:
    """Return the version a push releases, if it releases one, and why.

    A release is a push that leaves the version holding something it did not
    hold before, with no `.devN` suffix on it. That is exactly the state that
    merging a version-bump pull request leaves behind. A post-release bump
    writes a `.devN` version, so it reads as "not a release" without this
    having to know where the push came from.

    `before` is the version the branch held before the push, or None when
    there was nothing to read it from, which is a branch being created rather
    than a release being merged. The second half of the pair is a sentence for
    a log, and is there whichever way the decision went.
    """
    if before is None:
        return None, 'there was no version before this push'
    if before == after:
        return None, f'the version is still {after}'
    match = PIPELINE_VERSION_REGEX.match(after)
    if not match:
        # Not a shape that can be released, so not something to quietly
        # release anyway. Somebody hand-editing the version is the likely
        # cause.
        return None, f'{after!r} is not a version this pipeline releases'
    if match.group(5):
        return None, f'{after} is a development version'
    return after, f'{before} became {after}'


def is_prerelease(version: str) -> bool:
    """Return whether a version is an alpha, a beta or a release candidate."""
    match = PIPELINE_VERSION_REGEX.match(version)
    return bool(match and match.group(4))


def next_dev_version(released: str, branch: str) -> str:
    """Return the development version a branch goes to after a release.

    - a pre-release goes back to its own base version, so publishing 3.4.0b3
      leaves the branch working towards `3.4.0.dev0`;
    - a maintenance branch bumps the patch, so 2.23.5 leaves `2.23.6.dev0`;
    - anything else bumps the minor, so 3.8.2 leaves `3.9.0.dev0`.

    The pre-release test comes first, so a release candidate cut from a
    maintenance branch drops its suffix rather than bumping the patch.

    The answer is a placeholder rather than a prediction. It stops the tree
    claiming to be the version just released; nothing should count from it,
    because the next release is counted from the last tag.

    Raises:
        ValueError: if `released` is not a version this pipeline handles.
    """
    match = PIPELINE_VERSION_REGEX.match(released)
    if not match:
        raise ValueError(f'Not a version this pipeline can take apart: {released!r}')
    major, minor, patch, pre, _dev = match.groups()

    if pre is not None:
        # Only the pre-release suffix is checked, never `.devN`, so a
        # development version falls through to the bumps below. Nothing in a
        # pipeline built on `detect_release` reaches that, because it never
        # treats a `.devN` version as a release.
        return f'{major}.{minor}.{patch}.dev0'
    if branch.endswith(MAINTENANCE_BRANCH_SUFFIX):
        return f'{major}.{minor}.{int(patch) + 1}.dev0'
    return f'{major}.{int(minor) + 1}.0.dev0'


def resolve_branch(
    target: str,
    candidates: Sequence[str],
    containing: Sequence[str],
    *,
    default_branch: str = 'main',
) -> tuple[str, str]:
    """Return the branch a release was cut from, and why we think so.

    `target` is the release's `target_commitish`, `candidates` is every
    branch the repository releases from, and `containing` is the ones whose
    history has the released tag in it.

    A release drafted by a workflow usually carries a commit SHA as its
    `target_commitish`, so the name is no help and the containment answers
    it instead. A release made by hand through the web interface carries a
    branch name, and then the name is the better answer: it is what somebody
    chose.

    Containment on its own is ambiguous for a release cut from the default
    branch before a maintenance branch was taken off it, because the tag is in
    the history of both. The default branch is the right tie-break: a release
    really cut from a maintenance branch is never in the default branch's
    history, because that is what the maintenance branch is for.

    Raises:
        ValueError: if the branch cannot be worked out without guessing.
    """
    if containing:
        if target in containing:
            return target, f'the release names {target}, which has the tag in it'
        if len(containing) == 1:
            return containing[0], f'{containing[0]} is the only branch with the tag in it'
        names = ', '.join(containing)
        if default_branch in containing:
            return default_branch, f'{names} all have the tag in it, and {default_branch} wins'
        raise ValueError(
            f'{names} all have this tag in their history and none of them is '
            f'{default_branch}, so which branch was released is a guess. Open the '
            f'post-release pull request by hand.'
        )
    if target in candidates:
        # No tag in the checkout to place, but the release names a branch we
        # release from, so take it at its word.
        return target, f'the release names {target}, and the tag is not in the checkout'
    raise ValueError(
        f'No release branch has this tag in its history, and {target!r} is not one '
        f'of them ({", ".join(candidates) or "none found"}). Either the release was '
        f'cut from somewhere the caller does not know about, or the checkout is '
        f'missing the tag.'
    )
