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

"""Fix: copy the Code-of-Conduct template (link-only Ubuntu CoC) into the repo root.

Refuses to overwrite an existing file.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from ..common import ASSETS, repo_root

SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> int:
    """Copy the Code-of-Conduct template into place, and return the exit code."""
    try:
        os.chdir(repo_root())
    except OSError:
        return 3

    if Path('CODE_OF_CONDUCT.md').exists():
        sys.stderr.write('CODE_OF_CONDUCT.md already exists; refusing to overwrite.\n')
        return 1

    template = ASSETS / 'CODE_OF_CONDUCT.md'
    if not template.is_file():
        sys.stderr.write('Template missing.\n')
        return 3

    shutil.copy(template, 'CODE_OF_CONDUCT.md')
    sys.stdout.write(
        'Copied CODE_OF_CONDUCT.md. No placeholders to fill in — the link-only form is complete '
        'as-is.\n'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
