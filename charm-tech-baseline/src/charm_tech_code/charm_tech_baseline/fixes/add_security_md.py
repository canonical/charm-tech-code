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

"""Fix: copy the SECURITY.md template into the repo root.

Caller is the agent, which must then:
  1. Replace placeholder fields ({{REPO}}, {{CONTACT}}, etc.).
  2. Stage and commit; do not push without user direction.

This script never overwrites an existing SECURITY.md.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from ..common import ASSETS, repo_root

SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> int:
    """Copy the SECURITY.md template into place, and return the exit code."""
    try:
        os.chdir(repo_root())
    except OSError:
        return 3

    if Path('SECURITY.md').exists():
        sys.stderr.write(
            'SECURITY.md already exists; refusing to overwrite. Remove it first if the intent '
            'is to replace.\n'
        )
        return 1

    template = ASSETS / 'SECURITY.md.template'
    if not template.is_file():
        sys.stderr.write(f'Template missing at {template}\n')
        return 3

    shutil.copy(template, 'SECURITY.md')
    sys.stdout.write(
        'Copied SECURITY.md template. Replace placeholders ({{REPO}}, {{CONTACT}}) before '
        'committing.\n'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
