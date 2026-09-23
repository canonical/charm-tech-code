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

"""Fix: copy the Dependabot template into .github/.

Agent must edit the package-ecosystem set to match the repo
(drop unused ecosystems, uncomment gomod / docker if applicable).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from ..common import ASSETS, repo_root

SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> int:
    """Copy the Dependabot template into place, and return the exit code."""
    try:
        os.chdir(repo_root())
    except OSError:
        return 3

    if Path('.github/dependabot.yml').exists() or Path('.github/dependabot.yaml').exists():
        sys.stderr.write('.github/dependabot.{yml,yaml} already exists; refusing to overwrite.\n')
        return 1

    Path('.github').mkdir(parents=True, exist_ok=True)
    template = ASSETS / 'dependabot.yaml.template'
    if not template.is_file():
        sys.stderr.write('Template missing.\n')
        return 3

    shutil.copy(template, '.github/dependabot.yaml')
    sys.stdout.write(
        'Wrote .github/dependabot.yaml. Confirm the ecosystem set matches the repo '
        '(github-actions + uv by default; swap uv→pip or delete uv and uncomment gomod as '
        'needed), prune the `charm-tech` group to what this repo actually depends on, and '
        'confirm all dev tooling in use is covered by the `dev-tooling` group.\n'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
