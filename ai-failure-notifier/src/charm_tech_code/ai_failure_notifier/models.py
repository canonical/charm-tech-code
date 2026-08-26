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


"""The structured shapes a run's failure is reduced to."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

# --- Structured shapes ---
#
# The signature is built here, serialised into the prompt, and hashed for the
# marker, so its shape is worth pinning down rather than passing dicts around.
# `dataclasses.asdict` preserves field declaration order, which is what the
# prompt's JSON ends up in.


@dataclasses.dataclass(frozen=True)
class PytestFailure:
    """One line of pytest's short summary."""

    kind: str  # "FAILED" or "ERROR" -- pytest reports both here.
    test: str
    error: str


@dataclasses.dataclass(frozen=True)
class JobSignature:
    """What the deterministic parser could extract from one failed job's log."""

    job_id: int
    job_name: str
    failed_step: str | None
    pytest_failures: list[PytestFailure]
    go_failures: list[str]
    traceback_top_error: str | None
    tail_excerpt: list[str]


@dataclasses.dataclass(frozen=True)
class RunSignature:
    """Every failed job of one run, plus the run's own identifying fields."""

    run_id: str
    workflow_name: str
    html_url: str
    created_at: str
    jobs: list[JobSignature]

    def as_json(self) -> str:
        """Render for the prompt, in field declaration order."""
        return json.dumps(dataclasses.asdict(self), indent=2)


@dataclasses.dataclass(frozen=True)
class FailedJob:
    """A failed job as listed by `gh run view`, before its log is fetched."""

    id: int
    name: str
    failed_step: str | None


@dataclasses.dataclass(frozen=True)
class CandidateIssue:
    """An existing issue that might already track this failure."""

    number: int
    title: str
    body: str | None
    closed_at: str | None

    @classmethod
    def from_gh(cls, data: dict[str, Any]) -> CandidateIssue:
        """Build from one element of `gh issue list --json ...` output."""
        return cls(
            number=data['number'],
            title=data['title'],
            body=data.get('body'),
            closed_at=data.get('closedAt'),
        )

    def excerpt(self) -> str:
        """The first line of the body, bounded, for the candidate block."""
        lines = (self.body or '').strip().splitlines()
        return lines[0][:300] if lines else '(no body)'
