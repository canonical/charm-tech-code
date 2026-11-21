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


"""The per-repository configuration, read from the base branch."""

from __future__ import annotations

import dataclasses
import tomllib

PATH = '.github/review-tier.toml'


@dataclasses.dataclass(frozen=True)
class BotBranch:
    """One prints-charming-bot branch: the files it may change, and how."""

    files: frozenset[str]
    lines: str | None = None  # A regex every changed line must match.


@dataclasses.dataclass(frozen=True)
class Config:
    """Everything a repository says about its tiers."""

    team: frozenset[str]
    reviewers: frozenset[str]  # Whose approvals count.
    line_limit: int
    allow: tuple[str, ...]
    allow_except: tuple[str, ...]
    release_author: str
    release_branches: tuple[str, ...]
    release_files: frozenset[str]
    release_line_checked: frozenset[str]
    release_lockfile: str
    release_packages: frozenset[str]
    bot_author: str
    bot_branches: dict[str, BotBranch]
    label: str = 'full-review'


def parse(text: str) -> Config:
    """Parse the TOML configuration file.

    A missing key is an error, not a default, except for `reviewers`, which is
    the team list if it isn't given, and `label`.
    """
    try:
        d = tomllib.loads(text)
        release, bot = d['release'], d['bot']
        return Config(
            team=frozenset(login.lower() for login in d['team']),
            reviewers=frozenset(login.lower() for login in d.get('reviewers', d['team'])),
            line_limit=int(d['line-limit']),
            allow=tuple(d['low-risk']['allow']),
            allow_except=tuple(d['low-risk']['except']),
            release_author=release['author'],
            release_branches=tuple(release['branches']),
            release_files=frozenset(release['files']),
            release_line_checked=frozenset(release['line-checked']),
            release_lockfile=release['lockfile'],
            release_packages=frozenset(release['packages']),
            bot_author=bot['author'],
            bot_branches={
                name: BotBranch(frozenset(b['files']), b.get('lines'))
                for name, b in bot['branches'].items()
            },
            label=d.get('label', 'full-review'),
        )
    except KeyError as e:
        raise SystemExit(f'{PATH} is missing the {e.args[0]!r} key.') from None
