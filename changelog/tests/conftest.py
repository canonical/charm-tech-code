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

"""Nothing in this package may read the clock.

`format_changes` used to call `datetime.datetime.now()` itself, which is what
made the output of a release depend on which day CI happened to run and made
the function impossible to assert on. The date is an argument now, and this
fixture is what keeps it one: it replaces the `datetime` module as `_format`
sees it, so a reinstated `now()` or `today()` call fails the whole suite
rather than quietly passing on every day except the one that matters.
"""

from __future__ import annotations

import pytest

from charm_tech_code.changelog import _format


class _NoClock:
    """Stands in for `datetime.datetime` and `datetime.date`."""

    @staticmethod
    def now(*args: object, **kwargs: object):
        raise AssertionError(
            'The clock was read by the package itself. `format_changes` takes '
            'a date argument precisely so that it does not do this.'
        )

    today = now
    utcnow = now


class _NoClockModule:
    datetime = _NoClock
    date = _NoClock


@pytest.fixture(autouse=True)
def no_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_format, 'datetime', _NoClockModule)
