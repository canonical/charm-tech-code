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


"""The runner's step summary, written from both the gh layer and apply."""

from __future__ import annotations

import os
import sys


def write_step_summary(message: str) -> None:
    """Report a line to the job's step summary and to the log.

    Always goes to stderr as well as the summary: every fallback path in this
    script reports through here, and a fallback that only shows up in the
    summary is invisible to anyone reading the job log or the API.
    """
    print(message, file=sys.stderr)
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(message + '\n')
