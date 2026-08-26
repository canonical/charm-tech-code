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

"""Nothing in this suite may reach the network or run a real subprocess.

This is not belt-and-braces. The tests mock `gh` by patching the name on the
module they import, and `mock.patch.object` keeps succeeding when a refactor
moves that function to a different module -- the attribute is still there to
be patched, it is just no longer the one the call sites resolve. The suite
then shells out to the real `gh`, authenticated as whoever is running it,
against whatever repository the fixtures name.

That is not hypothetical. On 2026-08-26, splitting this package into modules
did exactly that, and the suite opened two issues and posted two comments on
a live repository before anyone noticed. The only visible symptom was the run
taking 35 seconds instead of a tenth of one.

So: any unpatched call fails loudly here, at the boundary, instead of
quietly succeeding somewhere real. A test that needs one of these mocks it
itself, which overrides this fixture for that test.
"""

from __future__ import annotations

import subprocess
import urllib.request

import pytest


def _blocked(name: str):
    def raise_instead(*args: object, **kwargs: object):
        raise AssertionError(
            f'{name} was called for real by a test. Nothing in this suite may '
            f'run a subprocess or reach the network -- a mock is missing, or '
            f'is patching a name the code no longer resolves. Called with: '
            f'{args!r} {kwargs!r}'
        )

    return raise_instead


@pytest.fixture(autouse=True)
def no_real_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    for attr in ('run', 'Popen', 'call', 'check_call', 'check_output'):
        monkeypatch.setattr(subprocess, attr, _blocked(f'subprocess.{attr}'))
    monkeypatch.setattr(urllib.request, 'urlopen', _blocked('urllib.request.urlopen'))
