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

"""Unit tests for the changelog package.

The specification here is what `canonical/operator`'s `release.py` does
against real input, so the two large fixtures are real operator releases
rather than invented ones. Both are reconstructed from the repository's own
history: `git log --reverse 3.8.1..3.8.2` gives the merged pull requests in
the range, in merge order, and GitHub's generated notes are one
`* <PR title> by @<user> in <url>` bullet each, in that same order, with the
PR title being the squash-commit subject minus its ` (#NNNN)` suffix.
"""

from __future__ import annotations

import datetime
import unittest

from charm_tech_code.changelog import (
    CATEGORIES,
    CATEGORY_HEADINGS,
    commit_type_to_category,
    format_changes,
    format_release_notes,
    parse_release_notes,
)

# canonical/operator 3.8.2, released 31 August 2026. Twenty-three merged pull
# requests, eleven of them `chore`. Ali-932's was genuinely their first
# contribution to the repository, so the "New Contributors" section is real
# too. The two bot handles (`@dependabot`, `@prints-charming-bot`) are the
# only part of this not taken straight from the commits; nothing depends on
# them, since the parser only requires a single unspaced token after `by`.
OPERATOR_3_8_2_NOTES = """\
## What's Changed
* chore: adjust versions after release by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2670
* docs: give each best-practice admonition a stable :name: anchor by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2524
* ci: point DB charm CI at the moved mysql-operators repo by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2551
* chore: bump cryptography from 48.0.1 to 50.0.0 by @dependabot in https://github.com/canonical/operator/pull/2682
* fix: compare full event paths when skipping duplicate notices by @Ali-932 in https://github.com/canonical/operator/pull/2684
* chore: bump the actions group across 1 directory with 8 updates by @dependabot in https://github.com/canonical/operator/pull/2674
* chore: bump the runtime group across 1 directory with 4 updates by @dependabot in https://github.com/canonical/operator/pull/2691
* docs: reword text that vale 3.17 flags as misspelled by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2695
* chore: update charm pins by @prints-charming-bot in https://github.com/canonical/operator/pull/2582
* chore: bump the dev-tooling group in /examples/httpbin-demo with 2 updates by @dependabot in https://github.com/canonical/operator/pull/2675
* chore: bump the charm-tech group across 1 directory with 3 updates by @dependabot in https://github.com/canonical/operator/pull/2697
* docs: stop styling page references as blockquotes by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2666
* ci: switch example charm integration tests to Concierge `k8s` preset by @dwilding in https://github.com/canonical/operator/pull/2696
* docs: make the custom-endpoint-name sample test actually test something by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2664
* ci: use the upstream concierge presets again by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2699
* docs: replace `requests` by `urllib` in K8s tutorial integration tests by @dwilding in https://github.com/canonical/operator/pull/2687
* fix: don't pass a message when converting an unknown status by name by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2700
* chore: bump the dev-tooling group with 4 updates by @dependabot in https://github.com/canonical/operator/pull/2676
* chore: update charm pins by @prints-charming-bot in https://github.com/canonical/operator/pull/2701
* chore: adopt ruff 0.16's new lint conventions by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2698
* docs: recommend spread directly, rather than charmcraft test by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2706
* docs: extract sections in how to write integration tests to their own howto guide by @tromai in https://github.com/canonical/operator/pull/2662
* chore: update changelog and versions for 3.8.2 release by @dwilding in https://github.com/canonical/operator/pull/2716

## New Contributors
* @Ali-932 made their first contribution in https://github.com/canonical/operator/pull/2684

**Full Changelog**: https://github.com/canonical/operator/compare/3.8.1...3.8.2
"""

# The PR numbers of the eleven `chore` pull requests in that release. None of
# them may appear anywhere in either rendered output.
OPERATOR_3_8_2_CHORE_PRS = (
    '2670',
    '2682',
    '2674',
    '2691',
    '2582',
    '2675',
    '2697',
    '2676',
    '2701',
    '2698',
    '2716',
)

# Four real pull requests from the 3.7.1..3.8.0 range, in merge order, one of
# them the only `!` pull request operator has merged into a 3.x release
# (#2585). Trimmed to four bullets because the full range is fifty; the point
# of this fixture is the `!`, not the volume.
OPERATOR_BREAKING_NOTES = """\
## What's Changed
* refactor: replace jsonpatch with an inline dict-diff by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2578
* refactor!: move the otlp-json package to be a regular ops-tracing module by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2585
* feat: note the socket path in Pebble tracing spans by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2555
* fix: tear down `Runtime.exec()` when the charm raises by @tonyandrewmeyer in https://github.com/canonical/operator/pull/2581

**Full Changelog**: https://github.com/canonical/operator/compare/3.7.1...3.8.0
"""


class RealReleaseTests(unittest.TestCase):
    """The 3.8.2 fixture, end to end."""

    def setUp(self):
        self.categories, self.full_changelog = parse_release_notes(OPERATOR_3_8_2_NOTES)

    def test_categories(self):
        # Twelve of the twenty-three pull requests survive, in merge order.
        assert self.categories == {
            'breaking': [],
            'feat': [],
            'fix': [
                (
                    'Compare full event paths when skipping duplicate notices',
                    'https://github.com/canonical/operator/pull/2684',
                ),
                (
                    "Don't pass a message when converting an unknown status by name",
                    'https://github.com/canonical/operator/pull/2700',
                ),
            ],
            'docs': [
                (
                    'Give each best-practice admonition a stable :name: anchor',
                    'https://github.com/canonical/operator/pull/2524',
                ),
                (
                    'Reword text that vale 3.17 flags as misspelled',
                    'https://github.com/canonical/operator/pull/2695',
                ),
                (
                    'Stop styling page references as blockquotes',
                    'https://github.com/canonical/operator/pull/2666',
                ),
                (
                    'Make the custom-endpoint-name sample test actually test something',
                    'https://github.com/canonical/operator/pull/2664',
                ),
                (
                    'Replace `requests` by `urllib` in K8s tutorial integration tests',
                    'https://github.com/canonical/operator/pull/2687',
                ),
                (
                    'Recommend spread directly, rather than charmcraft test',
                    'https://github.com/canonical/operator/pull/2706',
                ),
                (
                    'Extract sections in how to write integration tests to their own howto guide',
                    'https://github.com/canonical/operator/pull/2662',
                ),
            ],
            'test': [],
            'refactor': [],
            'perf': [],
            'ci': [
                (
                    'Point DB charm CI at the moved mysql-operators repo',
                    'https://github.com/canonical/operator/pull/2551',
                ),
                (
                    'Switch example charm integration tests to Concierge `k8s` preset',
                    'https://github.com/canonical/operator/pull/2696',
                ),
                (
                    'Use the upstream concierge presets again',
                    'https://github.com/canonical/operator/pull/2699',
                ),
            ],
            'revert': [],
        }

    def test_full_changelog_line(self):
        assert self.full_changelog == (
            '**Full Changelog**: https://github.com/canonical/operator/compare/3.8.1...3.8.2'
        )

    def test_chore_is_dropped(self):
        # Eleven of the twenty-three pull requests are `chore`, and none of
        # them reaches the output. Deliberate: dependency bumps, charm-pin
        # updates and the release's own version bump are not changelog
        # material.
        notes = format_release_notes(self.categories, self.full_changelog)
        entry = format_changes(self.categories, '3.8.2', datetime.date(2026, 8, 31))
        assert 'chore' not in notes.lower()
        assert 'chore' not in entry.lower()
        for pr in OPERATOR_3_8_2_CHORE_PRS:
            assert pr not in notes, f'chore PR #{pr} leaked into the release notes'
            assert pr not in entry, f'chore PR #{pr} leaked into the changelog entry'

    def test_new_contributors_section_is_dropped(self):
        notes = format_release_notes(self.categories, self.full_changelog)
        assert 'New Contributors' not in notes
        assert 'made their first contribution' not in notes

    def test_changes_entry(self):
        # This is the 3.8.2 entry as it appears in operator's CHANGES.md,
        # except for three summaries where the committed CHANGES.md was
        # edited by hand afterwards (#2700 gained an "In `ops.testing`,"
        # prefix, #2524 lost its ":name:", and #2662 was reworded). The
        # section order, the bullet order within each section and the
        # blank-line layout are all exactly what shipped.
        assert (
            format_changes(self.categories, '3.8.2', datetime.date(2026, 8, 31))
            == """\
# 3.8.2 - 31 August 2026

## Fixes

* Compare full event paths when skipping duplicate notices (#2684)
* Don't pass a message when converting an unknown status by name (#2700)

## Documentation

* Give each best-practice admonition a stable :name: anchor (#2524)
* Reword text that vale 3.17 flags as misspelled (#2695)
* Stop styling page references as blockquotes (#2666)
* Make the custom-endpoint-name sample test actually test something (#2664)
* Replace `requests` by `urllib` in K8s tutorial integration tests (#2687)
* Recommend spread directly, rather than charmcraft test (#2706)
* Extract sections in how to write integration tests to their own howto guide (#2662)

## CI

* Point DB charm CI at the moved mysql-operators repo (#2551)
* Switch example charm integration tests to Concierge `k8s` preset (#2696)
* Use the upstream concierge presets again (#2699)

"""
        )

    def test_release_notes(self):
        assert (
            format_release_notes(self.categories, self.full_changelog)
            == """\
## What's Changed

### Fixes
* Compare full event paths when skipping duplicate notices in https://github.com/canonical/operator/pull/2684
* Don't pass a message when converting an unknown status by name in https://github.com/canonical/operator/pull/2700

### Documentation
* Give each best-practice admonition a stable :name: anchor in https://github.com/canonical/operator/pull/2524
* Reword text that vale 3.17 flags as misspelled in https://github.com/canonical/operator/pull/2695
* Stop styling page references as blockquotes in https://github.com/canonical/operator/pull/2666
* Make the custom-endpoint-name sample test actually test something in https://github.com/canonical/operator/pull/2664
* Replace `requests` by `urllib` in K8s tutorial integration tests in https://github.com/canonical/operator/pull/2687
* Recommend spread directly, rather than charmcraft test in https://github.com/canonical/operator/pull/2706
* Extract sections in how to write integration tests to their own howto guide in https://github.com/canonical/operator/pull/2662

### CI
* Point DB charm CI at the moved mysql-operators repo in https://github.com/canonical/operator/pull/2551
* Switch example charm integration tests to Concierge `k8s` preset in https://github.com/canonical/operator/pull/2696
* Use the upstream concierge presets again in https://github.com/canonical/operator/pull/2699

**Full Changelog**: https://github.com/canonical/operator/compare/3.8.1...3.8.2"""
        )

    def test_the_date_is_the_one_it_is_given(self):
        entry = format_changes(self.categories, '3.8.2', datetime.date(2020, 1, 2))
        assert entry.startswith('# 3.8.2 - 02 January 2020\n')


class BreakingChangeTests(unittest.TestCase):
    """A `!` moves an entry into its own category, keeping its real type."""

    def setUp(self):
        self.categories, self.full_changelog = parse_release_notes(OPERATOR_BREAKING_NOTES)

    def test_breaking_entry_keeps_its_real_type_as_a_prefix(self):
        assert self.categories['breaking'] == [
            (
                'Refactor: Move the otlp-json package to be a regular ops-tracing module',
                'https://github.com/canonical/operator/pull/2585',
            )
        ]

    def test_breaking_entry_is_not_also_in_its_own_type(self):
        # The `!` moves the entry rather than copying it, so #2585 leaves
        # `refactor` and #2578, which has no `!`, is all that is left there.
        assert self.categories['refactor'] == [
            (
                'Replace jsonpatch with an inline dict-diff',
                'https://github.com/canonical/operator/pull/2578',
            )
        ]

    def test_release_notes_put_breaking_first_with_a_warning(self):
        assert (
            format_release_notes(self.categories, self.full_changelog)
            == """\
## What's Changed

### Breaking Changes
There are breaking changes in this release. Please review them carefully:

* Refactor: Move the otlp-json package to be a regular ops-tracing module in https://github.com/canonical/operator/pull/2585

### Features
* Note the socket path in Pebble tracing spans in https://github.com/canonical/operator/pull/2555

### Fixes
* Tear down `Runtime.exec()` when the charm raises in https://github.com/canonical/operator/pull/2581

### Refactoring
* Replace jsonpatch with an inline dict-diff in https://github.com/canonical/operator/pull/2578

**Full Changelog**: https://github.com/canonical/operator/compare/3.7.1...3.8.0"""
        )

    def test_changes_entry_puts_breaking_first_without_the_warning(self):
        # The warning sentence belongs to the release notes only. A
        # `CHANGES.md` entry is a list, and gets the heading alone.
        assert (
            format_changes(self.categories, '3.8.0', datetime.date(2026, 6, 30))
            == """\
# 3.8.0 - 30 June 2026

## Breaking Changes

* Refactor: Move the otlp-json package to be a regular ops-tracing module (#2585)

## Features

* Note the socket path in Pebble tracing spans (#2555)

## Fixes

* Tear down `Runtime.exec()` when the charm raises (#2581)

## Refactoring

* Replace jsonpatch with an inline dict-diff (#2578)

"""
        )


class ParseTests(unittest.TestCase):
    """The bullet format, in detail."""

    def parse(self, *bullets: str) -> dict[str, list[tuple[str, str]]]:
        categories, _ = parse_release_notes('\n'.join(bullets))
        return categories

    def test_summary_is_capitalised(self):
        # PR titles are lowercase after the conventional-commit type, and
        # changelog bullets are sentence case.
        categories = self.parse('* fix: do the thing by @someone in https://example.com/pull/1')
        assert categories['fix'] == [('Do the thing', 'https://example.com/pull/1')]

    def test_summary_that_starts_with_a_backtick_is_left_alone(self):
        categories = self.parse(
            '* fix: `Runtime.exec()` tears down by @someone in https://example.com/pull/1'
        )
        assert categories['fix'] == [('`Runtime.exec()` tears down', 'https://example.com/pull/1')]

    def test_unrecognised_type_is_dropped(self):
        # `build` and `style` are conventional-commit types the PR-title
        # check accepts, but they are not changelog categories, so they go
        # the same way `chore` does.
        categories = self.parse(
            '* build: bump the wheel by @someone in https://example.com/pull/1',
            '* style: reformat by @someone in https://example.com/pull/2',
            '* nonsense: whatever by @someone in https://example.com/pull/3',
        )
        assert all(not items for items in categories.values())

    def test_breaking_on_a_dropped_type_is_still_dropped(self):
        # The `!` is only honoured for a type that has a category, so a
        # `chore!` does not sneak into the changelog through the breaking
        # bucket.
        categories = self.parse(
            '* chore!: drop python 3.8 by @someone in https://example.com/pull/1'
        )
        assert categories['breaking'] == []

    def test_every_category_is_present_even_when_empty(self):
        # Callers index `categories['breaking']` directly, and iterate the
        # dict for the rendering order, so the shape does not depend on what
        # happened to be in the release.
        categories = self.parse('')
        assert list(categories) == list(CATEGORIES)

    def test_lines_that_are_not_bullets_are_ignored(self):
        categories, full_changelog = parse_release_notes(
            "## What's Changed\n"
            'Some prose about the release.\n'
            '* not a conventional commit title by @someone in https://example.com/pull/1\n'
            '* fix: a real one by @someone in https://example.com/pull/2\n'
        )
        assert categories['fix'] == [('A real one', 'https://example.com/pull/2')]
        assert full_changelog is None

    def test_indented_bullets_are_parsed(self):
        assert self.parse('    * fix: indented by @someone in https://example.com/pull/1')['fix']

    def test_new_contributors_section_is_stripped_before_parsing(self):
        # It is stripped rather than skipped, because its bullets are the
        # same shape and would otherwise have to be excluded by luck.
        categories, _ = parse_release_notes(
            '* fix: a real one by @someone in https://example.com/pull/1\n'
            '\n'
            '## New Contributors\n'
            '* @someone made their first contribution in https://example.com/pull/1\n'
        )
        assert categories['fix'] == [('A real one', 'https://example.com/pull/1')]


class FormatReleaseNotesTests(unittest.TestCase):
    def empty(self) -> dict[str, list[tuple[str, str]]]:
        return {category: [] for category in CATEGORIES}

    def test_empty_release(self):
        assert format_release_notes(self.empty(), None) == "## What's Changed\n"

    def test_categories_render_in_the_declared_order(self):
        categories = self.empty()
        for category in ('revert', 'ci', 'feat', 'fix'):
            categories[category] = [(f'A {category} change', 'https://example.com/pull/1')]
        headings = [
            line
            for line in format_release_notes(categories, None).splitlines()
            if line.startswith('###')
        ]
        assert headings == ['### Features', '### Fixes', '### CI', '### Reverted']

    def test_full_changelog_is_appended_when_given(self):
        notes = format_release_notes(self.empty(), '**Full Changelog**: https://example.com/x')
        assert notes.endswith('**Full Changelog**: https://example.com/x')


class FormatChangesTests(unittest.TestCase):
    def entry(self, pr_link: str) -> str:
        categories = {category: [] for category in CATEGORIES}
        categories['fix'] = [('A fix', pr_link)]
        return format_changes(categories, '1.2.3', datetime.date(2026, 9, 10))

    def test_pr_number_comes_from_the_link(self):
        assert '* A fix (#2684)' in self.entry('https://github.com/canonical/operator/pull/2684')

    def test_an_unrecognisable_link_gets_a_question_mark(self):
        # An entry with no PR to point at still belongs in the changelog, so
        # this is a placeholder rather than a failure.
        assert '* A fix (#?)' in self.entry('https://github.com/canonical/operator/commit/abc123')

    def test_empty_release(self):
        empty = {category: [] for category in CATEGORIES}
        assert format_changes(empty, '1.2.3', datetime.date(2026, 9, 10)) == (
            '# 1.2.3 - 10 September 2026\n\n'
        )

    def test_the_tag_is_used_verbatim(self):
        empty = {category: [] for category in CATEGORIES}
        assert format_changes(empty, '3.4.0b1', datetime.date(2026, 9, 10)).startswith(
            '# 3.4.0b1 - '
        )


class CommitTypeToCategoryTests(unittest.TestCase):
    def test_known_types(self):
        assert commit_type_to_category('feat') == 'Features'
        assert commit_type_to_category('fix') == 'Fixes'
        assert commit_type_to_category('docs') == 'Documentation'
        assert commit_type_to_category('test') == 'Tests'
        assert commit_type_to_category('ci') == 'CI'
        assert commit_type_to_category('perf') == 'Performance'
        assert commit_type_to_category('refactor') == 'Refactoring'
        assert commit_type_to_category('revert') == 'Reverted'
        assert commit_type_to_category('breaking') == 'Breaking Changes'

    def test_unknown_type_is_capitalised(self):
        assert commit_type_to_category('whatever') == 'Whatever'

    def test_chore_has_no_category(self):
        # It has no heading because it is not a category. That it still
        # returns something readable is a property of the fallback, not an
        # invitation to render it.
        assert 'chore' not in CATEGORY_HEADINGS
        assert 'chore' not in CATEGORIES

    def test_every_category_has_a_heading(self):
        # Otherwise a category would render under a capitalised version of
        # its own key, which is only ever right by accident.
        assert set(CATEGORIES) <= set(CATEGORY_HEADINGS)
