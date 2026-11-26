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


"""Who gets credited in a changelog, and how.

**"Outside the team" is not "outside Canonical".** A contributor from
another Canonical team has an `@canonical.com` address, no GitHub handle
anyone can derive from it, and every bit as much claim to the credit as a
stranger does. They are credited by name when nothing better is known.

**The pull request's author is the best answer, when there is one.** A git
log only has a name and an email, and an author who commits from a real
address has no handle anyone can derive from them. The pull request a
commit came from does know its author's login, so a caller who has looked
that up passes it in, and it wins over anything the log says.
"""

from __future__ import annotations

from collections.abc import Collection

from ._constants import NOREPLY_EMAIL_REGEX


def normalise_team(team: Collection[str]) -> frozenset[str]:
    """Fold a caller's team list into something to compare against.

    Entries may be email addresses or GitHub handles, with or without a
    leading `@`, in any mixture: a caller assembling the list from a team
    page has both to hand and should not have to decide which kind each one
    is. Comparison is case-insensitive, since neither an email address nor a
    GitHub handle distinguishes case.
    """
    return frozenset(member.strip().lstrip('@').casefold() for member in team if member.strip())


def derive_handle(email: str) -> str | None:
    """Recover a GitHub handle from an author email, if it is in there.

    Only a `users.noreply.github.com` address carries one. That is not the
    narrow case it sounds like: it is what GitHub commits as by default when
    an account keeps its email private, so it is the usual form for a
    drive-by contributor, which is the author this most needs to name.

    Returns:
        The handle without its `@`, or `None` for any other address.
    """
    match = NOREPLY_EMAIL_REGEX.match(email.strip())
    return match.group('handle') if match else None


def credit_for(
    name: str, email: str, team: Collection[str], *, login: str | None = None
) -> str | None:
    """Work out how to credit the author of a commit, from a git log.

    Args:
        name: The author name, as `%an` gives it.
        email: The author email, as `%ae` gives it.
        team: The maintainers, as emails and/or handles. See `normalise_team`.
            A parameter rather than a constant because it drifts and differs
            per repository. An empty team credits everyone, which is the
            right way for this to fail: over-crediting is visible in a draft
            release and takes one edit, while crediting nobody is invisible
            until a contributor notices.
        login: The GitHub login of the author of the pull request the commit
            came from, if the caller looked it up. When given, it decides the
            credit on its own, and `name` and `email` are not consulted.

    Returns:
        `@handle` when there is a login or a handle can be recovered from the
        email, the name when neither is available, or `None` when this
        author is one of `team` and so is not a guest to be thanked.
    """
    members = normalise_team(team)
    if login is not None and login.strip().lstrip('@'):
        login = login.strip().lstrip('@')
        return None if login.casefold() in members else f'@{login}'
    handle = derive_handle(email)
    if email.strip().casefold() in members:
        return None
    if handle is not None and handle.casefold() in members:
        return None
    return f'@{handle}' if handle is not None else name.strip() or None
