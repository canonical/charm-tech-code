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


"""Unit tests for the release-pipeline decisions and the release body.

The versions and branch names are the shapes canonical/operator releases
(`main`, `2.23-maintenance`, `3.9.0rc1`, ...). The changelog and release
notes prose is invented.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
from unittest import mock

import pytest

from charm_tech_code.changelog import _cli
from charm_tech_code.changelog._release import (
    detect_release,
    is_prerelease,
    next_dev_version,
    resolve_branch,
)
from charm_tech_code.changelog._release_body import (
    changelog_section,
    is_placeholder,
    release_body,
    release_notes_from_description,
)

# The shape a release pull request's description has, down to the blank lines
# around the markers. Everything outside them is for the reviewers.
DESCRIPTION = """Prepares the 3.8.3 release from `main`.

* `CHANGES.md` has a new entry for 3.8.3.
* [Commits since 3.8.2](https://github.com/canonical/operator/compare/3.8.2...main)

The release notes below become the body of the GitHub release. Edit them here: this description is where they are read from.

<!-- release-notes:start -->

A routine maintenance release: two fixes and a documentation pass.

## Fixes

The kettle no longer reports itself boiled while it is still cold.

<!-- release-notes:end -->
"""  # noqa: E501 - a pull request description is not hard-wrapped.

PLACEHOLDER_DESCRIPTION = (
    'Prepares the 3.8.3 release from `main`.\n'
    '\n'
    '<!-- release-notes:start -->\n'
    '\n'
    '_No release notes were drafted for 3.8.3: no OPENROUTER_API_KEY is configured._\n'
    '\n'
    'Write them here before merging. They become the body of the GitHub release,'
    ' above the changelog entry for this version.\n'
    '\n'
    '<!-- release-notes:end -->\n'
)

# Two sections, so that the slice has somewhere to stop.
CHANGES = """# 3.8.3 - 22 September 2026

## Fixes

* Stop the kettle reporting itself boiled while cold ([#101](https://example.com/101))

## Documentation

* Explain which way up the teapot goes ([#102](https://example.com/102))

# 3.8.2 - 31 August 2026

## Fixes

* Warm the pot before pouring (#100)
"""


class TestDetectRelease:
    """Deciding whether a push released something."""

    def test_a_release(self):
        """The merge of a version-bump pull request is the case that matters."""
        assert detect_release('3.9.0.dev0', '3.9.0')[0] == '3.9.0'

    def test_a_patch_release_on_a_maintenance_branch(self):
        """A maintenance branch releases the same way, and this does not know the difference."""
        assert detect_release('2.23.5.dev0', '2.23.6')[0] == '2.23.6'

    def test_a_release_candidate(self):
        """A release candidate is a release, marked as a pre-release."""
        assert detect_release('3.9.0.dev0', '3.9.0rc1')[0] == '3.9.0rc1'
        assert is_prerelease('3.9.0rc1')
        assert is_prerelease('3.9.0a1')
        assert is_prerelease('3.9.0b2')
        assert not is_prerelease('3.9.0')

    def test_the_post_release_bump_is_not_a_release(self):
        """The bump back to a development version changes the version, and releases nothing."""
        version, why = detect_release('3.9.0', '3.10.0.dev0')
        assert version is None
        assert 'development version' in why

    def test_an_unchanged_version_is_not_a_release(self):
        """Nearly every push: the file was touched, the version was not."""
        assert detect_release('3.9.0.dev0', '3.9.0.dev0')[0] is None

    def test_a_new_branch_is_not_a_release(self):
        """Nothing to compare against means nothing was released."""
        assert detect_release(None, '3.9.0')[0] is None

    def test_an_unreleasable_version_is_not_a_release(self):
        """A hand-edited version of some other shape is left alone."""
        version, why = detect_release('3.9.0.dev0', '3.9')
        assert version is None
        assert 'not a version' in why


class TestNextDevVersion:
    """The development version a branch goes to after a release."""

    @pytest.mark.parametrize(
        ('released', 'expected'),
        [
            ('3.8.2', '3.9.0.dev0'),
            ('3.8.1', '3.9.0.dev0'),
            ('3.8.0', '3.9.0.dev0'),
            ('3.4.0', '3.5.0.dev0'),
        ],
    )
    def test_the_default_branch_bumps_the_minor(self, released: str, expected: str):
        assert next_dev_version(released, 'main') == expected

    @pytest.mark.parametrize(
        ('released', 'expected'),
        [
            ('2.23.5', '2.23.6.dev0'),
            ('2.23.4', '2.23.5.dev0'),
            ('2.23.2', '2.23.3.dev0'),
        ],
    )
    def test_a_maintenance_branch_bumps_the_patch(self, released: str, expected: str):
        assert next_dev_version(released, '2.23-maintenance') == expected

    @pytest.mark.parametrize(
        ('released', 'expected'),
        [
            ('3.4.0b3', '3.4.0.dev0'),
            ('3.4.0b1', '3.4.0.dev0'),
            ('3.4.0a1', '3.4.0.dev0'),
            ('3.9.0rc2', '3.9.0.dev0'),
        ],
    )
    def test_pre_releases_drop_their_suffix(self, released: str, expected: str):
        """A pre-release goes back to its own base version, bumping nothing."""
        assert next_dev_version(released, 'main') == expected

    def test_a_pre_release_on_a_maintenance_branch_still_drops_its_suffix(self):
        """The pre-release test comes before the branch name, so the patch stays put."""
        assert next_dev_version('2.23.6rc1', '2.23-maintenance') == '2.23.6.dev0'

    @pytest.mark.parametrize(
        ('released', 'branch', 'expected'),
        [
            ('9.9.9', 'main', '9.10.0.dev0'),
            ('9.9.9', '1.5-maintenance', '9.9.10.dev0'),
            ('3.0.0', 'main', '3.1.0.dev0'),
            ('2.23.9', '2.23-maintenance', '2.23.10.dev0'),
        ],
    )
    def test_the_bump_is_arithmetic_and_not_string_work(
        self, released: str, branch: str, expected: str
    ):
        """9 goes to 10 rather than to 0, on either half of the version."""
        assert next_dev_version(released, branch) == expected

    def test_a_development_version_falls_through_to_the_bumps(self):
        """Unreachable through the pipeline, but only the pre-release suffix is checked."""
        assert next_dev_version('3.9.0.dev0', 'main') == '3.10.0.dev0'

    @pytest.mark.parametrize('released', ['v3.8.2', '3.8', '3.8.2.post1', '3.8.2-rc1', ''])
    def test_a_version_of_another_shape_is_refused(self, released: str):
        """A tag of another shape is an error, not a guess."""
        with pytest.raises(ValueError):
            next_dev_version(released, 'main')


# Every branch a repository releases from, in `git for-each-ref` order rather
# than version order.
CANDIDATES = [
    '1.5-maintenance',
    '2.16-maintenance',
    '2.19-maintenance',
    '2.23-maintenance',
    '2.5-maintenance',
    '3.3-maintenance',
    'main',
]


class TestResolveBranch:
    """Getting from a published release to the branch it was cut from."""

    def test_a_draft_from_a_workflow_carries_a_sha_and_the_tag_places_it(self):
        """The target is a merge commit, so the name is no help and the tag answers it."""
        branch, why = resolve_branch(
            '0d7fbd21ad9d4a9e2e0f53b96e0b1a1f7ac8c7dd', CANDIDATES, ['main']
        )
        assert branch == 'main'
        assert 'only branch' in why

    def test_a_maintenance_release_is_on_its_own_branch_alone(self):
        """The default branch does not have it, which is what the maintenance branch is for."""
        branch, _ = resolve_branch('938e064b', CANDIDATES, ['2.23-maintenance'])
        assert branch == '2.23-maintenance'

    @pytest.mark.parametrize(
        'containing',
        [
            ['main', '2.23-maintenance', '3.3-maintenance'],
            ['main', '3.3-maintenance'],
        ],
    )
    def test_main_wins_when_several_branches_have_the_tag(self, containing: list[str]):
        """A release cut from `main` before a branch was taken off it is still `main`'s."""
        branch, why = resolve_branch('deadbeef', CANDIDATES, containing)
        assert branch == 'main'
        assert 'main wins' in why

    def test_the_default_branch_can_be_named(self):
        """A repository whose default branch is not `main` says so."""
        candidates = ['master', '1.4-maintenance']
        branch, why = resolve_branch(
            'deadbeef', candidates, ['master', '1.4-maintenance'], default_branch='master'
        )
        assert branch == 'master'
        assert 'master wins' in why

    def test_a_named_branch_is_taken_at_its_word(self):
        """A release made by hand carries a branch name rather than a SHA."""
        branch, why = resolve_branch('2.23-maintenance', CANDIDATES, ['main', '2.23-maintenance'])
        assert branch == '2.23-maintenance'
        assert 'names 2.23-maintenance' in why

    def test_a_named_branch_without_the_tag_does_not_win(self):
        """The name is a hint: if that branch has not got the tag, containment decides."""
        branch, _ = resolve_branch('main', CANDIDATES, ['2.23-maintenance'])
        assert branch == '2.23-maintenance'

    def test_a_named_branch_is_enough_when_the_tag_is_not_in_the_checkout(self):
        """With nothing to place the tag against, the name is all there is."""
        branch, why = resolve_branch('main', CANDIDATES, [])
        assert branch == 'main'
        assert 'not in the checkout' in why

    def test_nothing_to_go_on_is_an_error(self):
        """No containment and a target that names no release branch: stop."""
        with pytest.raises(ValueError, match='No release branch'):
            resolve_branch('deadbeef', CANDIDATES, [])

    def test_several_maintenance_branches_and_no_default_is_an_error(self):
        """It would be a guess rather than a wrong answer, so it is loud."""
        with pytest.raises(ValueError, match='is a guess'):
            resolve_branch('deadbeef', CANDIDATES, ['2.19-maintenance', '2.23-maintenance'])

    def test_the_branch_it_picks_is_what_the_arithmetic_reads(self):
        """The two halves joined up: the branch decides the bump."""
        branch, _ = resolve_branch('deadbeef', CANDIDATES, ['2.23-maintenance'])
        assert next_dev_version('2.23.5', branch) == '2.23.6.dev0'


class TestReleaseNotesFromDescription:
    """Lifting the notes back out of the merged pull request's description."""

    def test_takes_what_is_between_the_markers(self):
        """The notes, and none of the text written for the reviewers."""
        notes = release_notes_from_description(DESCRIPTION)
        assert notes.startswith('A routine maintenance release')
        assert notes.endswith('while it is still cold.')
        assert 'Prepares the 3.8.3 release' not in notes
        assert 'release-notes:' not in notes

    def test_takes_a_human_edited_body(self):
        """The point of the gate is that somebody rewrote these before merging."""
        edited = DESCRIPTION.replace(
            'A routine maintenance release: two fixes and a documentation pass.',
            'Mostly fixes. If your kettle lied to you, this is the release you want.\n\n'
            'Thanks to everyone who reported it.',
        )
        notes = release_notes_from_description(edited)
        assert notes.startswith('Mostly fixes.')
        assert 'Thanks to everyone who reported it.' in notes

    def test_takes_the_placeholder(self):
        """A merged placeholder is somebody's decision, not a failure."""
        notes = release_notes_from_description(PLACEHOLDER_DESCRIPTION)
        assert is_placeholder(notes)
        assert 'Write them here before merging.' in notes

    def test_ordinary_notes_are_not_the_placeholder(self):
        """The placeholder check does not fire on notes that merely mention it."""
        assert not is_placeholder(release_notes_from_description(DESCRIPTION))

    def test_rejects_a_missing_start_marker(self):
        """Without both markers there is no telling where the notes begin."""
        with pytest.raises(ValueError, match='0 `<!-- release-notes:start -->` markers'):
            release_notes_from_description(
                DESCRIPTION.replace('<!-- release-notes:start -->\n\n', '')
            )

    def test_rejects_a_missing_end_marker(self):
        """The end marker is the one an edit is most likely to take with it."""
        with pytest.raises(ValueError, match='0 `<!-- release-notes:end -->` markers'):
            release_notes_from_description(
                DESCRIPTION.replace('\n<!-- release-notes:end -->\n', '')
            )

    def test_rejects_a_duplicated_marker(self):
        """Two starts, from a copied-in draft, would silently drop half the notes."""
        with pytest.raises(ValueError, match='2 `<!-- release-notes:start -->` markers'):
            release_notes_from_description(
                DESCRIPTION.replace(
                    'A routine maintenance release',
                    '<!-- release-notes:start -->\n\nA routine maintenance release',
                )
            )

    def test_rejects_markers_in_the_wrong_order(self):
        """An end above a start is not an empty set of notes, it is a mistake."""
        swapped = DESCRIPTION.replace('start -->', 'TEMP -->')
        swapped = swapped.replace('end -->', 'start -->').replace('TEMP -->', 'end -->')
        with pytest.raises(ValueError, match='before it starts'):
            release_notes_from_description(swapped)

    def test_rejects_empty_notes(self):
        """Somebody deleted the notes rather than editing them."""
        with pytest.raises(ValueError, match='nothing between'):
            release_notes_from_description(
                'Prepares it.\n\n<!-- release-notes:start -->\n\n<!-- release-notes:end -->\n'
            )

    def test_allows_an_indented_marker(self):
        """A stray space before a marker is not worth failing a release over."""
        assert release_notes_from_description(
            DESCRIPTION.replace('<!-- release', '  <!-- release')
        )


class TestChangelogSection:
    """Slicing this release's entry out of a CHANGES.md."""

    def test_takes_the_first_section(self):
        """From its own heading to the previous release's, and no further."""
        section = changelog_section(CHANGES, '3.8.3')
        assert section.startswith('# 3.8.3 - 22 September 2026')
        assert '## Documentation' in section
        assert '3.8.2' not in section

    def test_takes_a_changelog_with_one_section(self):
        """A first release has no next heading to stop at."""
        only = '# 1.0.0 - 1 January 2027\n\n## Features\n\n* Everything (#1)\n'
        assert changelog_section(only, '1.0.0').endswith('* Everything (#1)')

    def test_ignores_blank_lines_above_the_heading(self):
        """The slice does not depend on the file starting at byte zero."""
        assert changelog_section('\n\n' + CHANGES, '3.8.3').startswith('# 3.8.3')

    def test_rejects_a_section_for_another_version(self):
        """The wrong changelog under the right notes is worse than no release."""
        with pytest.raises(ValueError, match=re.escape('first section is for 3.8.3')):
            changelog_section(CHANGES, '3.8.4')

    def test_rejects_a_changelog_that_does_not_start_with_a_heading(self):
        """If the file is not the shape we think, the slice would be guesswork."""
        with pytest.raises(ValueError, match='does not start with'):
            changelog_section('Changes are listed below.\n\n' + CHANGES, '3.8.3')


class TestReleaseBody:
    """The two halves, put together."""

    def test_notes_first_then_the_changelog(self):
        """What the release is about, and then the complete list."""
        body = release_body(
            release_notes_from_description(DESCRIPTION), changelog_section(CHANGES, '3.8.3')
        )
        assert body.startswith('A routine maintenance release')
        assert body.index('## Changelog') > body.index('A routine maintenance release')

    def test_the_changelog_keeps_its_entries_exactly(self):
        """Copied, not regenerated: every line of it survives unchanged."""
        section = changelog_section(CHANGES, '3.8.3')
        body = release_body('The notes.', section)
        entries = [line for line in section.splitlines() if line.startswith('* ')]
        assert len(entries) == 2
        for entry in entries:
            assert entry in body

    def test_the_headings_are_demoted(self):
        """The release has the version as its title and the notes use `##`."""
        body = release_body('The notes.', changelog_section(CHANGES, '3.8.3'))
        assert '\n### Fixes\n' in body
        assert '\n## Fixes\n' not in body
        assert '# 3.8.3 - 22 September 2026' not in body

    def test_the_placeholder_goes_in_as_it_stands(self):
        """A release drafted without a model still gets its changelog half."""
        body = release_body(
            release_notes_from_description(PLACEHOLDER_DESCRIPTION),
            changelog_section(CHANGES, '3.8.3'),
        )
        assert body.startswith('_No release notes were drafted for 3.8.3')
        assert '### Fixes' in body


class TestReleaseConsoleScript:
    """The three release subcommands, as a workflow step runs them."""

    def run_cli(self, *argv: str, stdin: str = '') -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch('sys.stdin', io.StringIO(stdin)),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            returncode = _cli.main(argv)
        return returncode, out.getvalue(), err.getvalue()

    def test_detect_release_prints_the_outputs_for_a_release(self):
        returncode, out, err = self.run_cli(
            'detect-release', '--before', '3.9.0.dev0', '--after', '3.9.0rc1'
        )
        assert returncode == 0
        assert out == 'version=3.9.0rc1\nprerelease=true\n'
        assert 'Releasing 3.9.0rc1' in err

    def test_detect_release_prints_nothing_for_an_ordinary_merge(self):
        returncode, out, err = self.run_cli(
            'detect-release', '--before', '3.9.0.dev0', '--after', '3.9.0.dev0'
        )
        assert (returncode, out) == (0, '')
        assert 'Not a release' in err

    def test_detect_release_prints_nothing_without_a_before(self):
        # An empty --before is how a workflow says "there was no file", since
        # it builds the argument from a variable that may be empty.
        for argv in (('--after', '3.9.0'), ('--before', '', '--after', '3.9.0')):
            returncode, out, _ = self.run_cli('detect-release', *argv)
            assert (returncode, out) == (0, '')

    def test_post_release_prints_the_branch_and_the_version(self):
        returncode, out, err = self.run_cli(
            'post-release',
            '--tag',
            '2.23.5',
            '--target',
            '938e064b',
            '--candidates',
            ',main,2.23-maintenance',
            '--containing',
            ',2.23-maintenance',
        )
        assert returncode == 0
        assert out == 'branch=2.23-maintenance\nversion=2.23.6.dev0\n'
        assert '2.23.5 was released from 2.23-maintenance' in err

    def test_post_release_takes_a_default_branch(self):
        returncode, out, _ = self.run_cli(
            'post-release',
            '--tag',
            '1.5.0',
            '--candidates',
            'master,1.4-maintenance',
            '--containing',
            'master,1.4-maintenance',
            '--default-branch',
            'master',
        )
        assert returncode == 0
        assert out == 'branch=master\nversion=1.6.0.dev0\n'

    def test_post_release_that_cannot_work_out_the_branch_prints_nothing(self):
        # Nothing on stdout, so a failed step cannot half-write $GITHUB_OUTPUT.
        returncode, out, err = self.run_cli(
            'post-release', '--tag', '3.8.3', '--target', 'deadbeef', '--candidates', 'main'
        )
        assert (returncode, out) == (2, '')
        assert 'No release branch' in err

    def test_post_release_refuses_a_tag_it_cannot_take_apart(self):
        returncode, out, _ = self.run_cli(
            'post-release',
            '--tag',
            'v3.8.3',
            '--target',
            'main',
            '--candidates',
            'main',
            '--containing',
            'main',
        )
        assert (returncode, out) == (2, '')

    def test_release_body_prints_the_body(self, tmp_path: pathlib.Path):
        changes = tmp_path / 'CHANGES.md'
        changes.write_text(CHANGES)
        returncode, out, _ = self.run_cli(
            'release-body', '--version', '3.8.3', '--changes', str(changes), stdin=DESCRIPTION
        )
        assert returncode == 0
        assert out == release_body(
            release_notes_from_description(DESCRIPTION), changelog_section(CHANGES, '3.8.3')
        )

    def test_release_body_reports_the_placeholder_without_failing(self, tmp_path: pathlib.Path):
        changes = tmp_path / 'CHANGES.md'
        changes.write_text(CHANGES)
        returncode, out, err = self.run_cli(
            'release-body',
            '--version',
            '3.8.3',
            '--changes',
            str(changes),
            stdin=PLACEHOLDER_DESCRIPTION,
        )
        assert returncode == 0
        assert out.startswith('_No release notes were drafted')
        assert 'placeholder' in err

    def test_release_body_fails_on_a_description_without_markers(self, tmp_path: pathlib.Path):
        # The one case that stops a release: no notes to publish.
        changes = tmp_path / 'CHANGES.md'
        changes.write_text(CHANGES)
        returncode, out, err = self.run_cli(
            'release-body',
            '--version',
            '3.8.3',
            '--changes',
            str(changes),
            stdin='Prepares the 3.8.3 release.\n',
        )
        assert (returncode, out) == (2, '')
        assert 'markers' in err

    def test_release_body_fails_on_a_missing_changelog(self, tmp_path: pathlib.Path):
        returncode, out, _ = self.run_cli(
            'release-body',
            '--version',
            '3.8.3',
            '--changes',
            str(tmp_path / 'nope.md'),
            stdin=DESCRIPTION,
        )
        assert (returncode, out) == (2, '')
