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

"""Fix: copy the AGENTS.md template into the repo root.
Agent must fill in {{...}} placeholders before committing — the
template is intentionally a skeleton, not a working file.
"""

from __future__ import annotations

import pathlib
import shutil
import sys

from .. import _common

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def main() -> int:
    try:
        import os

        os.chdir(_common.repo_root())
    except OSError:
        return 3

    if pathlib.Path('AGENTS.md').exists():
        sys.stderr.write('AGENTS.md already exists; refusing to overwrite.\n')
        return 1

    template = _common.ASSETS / 'AGENTS.md.template'
    if not template.is_file():
        sys.stderr.write('Template missing.\n')
        return 3

    shutil.copy(template, 'AGENTS.md')
    sys.stdout.write(
        'Copied AGENTS.md template. Replace {{REPO_DESCRIPTION_ONE_SENTENCE}}, '
        '{{SETUP_COMMANDS}}, {{TEST_COMMANDS}}, {{LINT_COMMANDS}}, {{DEPTH_LINK_TITLE}}, '
        '{{DEPTH_LINK}} before committing.\n'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
