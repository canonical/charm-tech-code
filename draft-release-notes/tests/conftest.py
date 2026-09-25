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


"""Nothing in this suite may reach the network.

A test that wants a response patches `urllib.request.urlopen` itself; one that
forgets fails here rather than spending an OpenRouter credit.
"""

from __future__ import annotations

import urllib.request

import pytest


def _blocked(*args: object, **kwargs: object):
    raise AssertionError(
        'urllib.request.urlopen was called for real by a test. Nothing in this '
        f'suite may reach the network -- a mock is missing. Called with: {args!r} {kwargs!r}'
    )


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, 'urlopen', _blocked)
    # Whatever the environment running the tests holds, the tests decide.
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.delenv('OPENROUTER_MODEL', raising=False)
