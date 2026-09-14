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
against real input, so the large fixtures are real operator releases rather
than invented ones. The notes fixtures and the commit fixtures describe the
same pull requests from the two ends: `git log --reverse 3.8.1..3.8.2` gives
the merged pull requests in the range, in merge order, and GitHub's generated
notes are one `* <PR title> by @<user> in <url>` bullet each, in that same
order, with the PR title being the squash-commit subject minus its ` (#NNNN)`
suffix.

**Which fixtures are observed and which are constructed** matters enough to
say per fixture, and each one says so. The short version: everything taken
from `canonical/operator` is observed, down to the author emails, except the
two bot handles in the 3.8.2 notes; and the revert cases in `RevertTests`
are constructed, because operator's history contains exactly one revert and
it reverts a `chore`, which the changelog drops anyway.

Commit *bodies* are the one thing elided from the observed fixtures. A real
`git log` body is the whole pull-request description, which is kilobytes per
commit and none of which is read except a `Reverts owner/repo#N` line, so the
fixtures carry the bodies that matter and empty strings everywhere else.
"""

from __future__ import annotations

import contextlib
import datetime
import io
import pathlib
import unittest
from unittest import mock

from charm_tech_code.changelog import (
    CATEGORIES,
    CATEGORY_HEADINGS,
    GIT_LOG_FORMAT,
    MINOR,
    MINOR_BUMP_CATEGORIES,
    PATCH,
    Change,
    _cli,
    commit_type_to_category,
    format_changes,
    format_release_notes,
    infer_bump_size,
    next_version,
    parse_git_log,
)

# The Charm Tech team as `canonical/operator` would supply it: emails, which
# is what a git log carries, and handles, which is what release notes carry.
# Observed -- the handles are the team list in the staging tree's AGENTS.md
# and the emails are the ones in operator's own history. Two bot addresses
# are in here as well, because a bot is not a contributor to thank either;
# nothing in these tests depends on that, since every bot commit in the
# fixtures is a `chore` and dropped before it could be credited.
OPERATOR_TEAM = (
    '@benhoyt',
    '@dwilding',
    '@hpidcock',
    '@james-garner-canonical',
    '@tromai',
    '@tonyandrewmeyer',
    'ben.hoyt@canonical.com',
    'david.wilding@canonical.com',
    'tony.meyer@canonical.com',
    'trongnhan.mai@canonical.com',
    'ben.hoyt+prints-charming-bot@canonical.com',
    '49699333+dependabot[bot]@users.noreply.github.com',
)

#: The repository every fixture here comes from, and so the one the
#: pull-request links are built against.
REPO = 'canonical/operator'

TONY = ('Tony Meyer', 'tony.meyer@canonical.com')
DAVID = ('Dave Wilding', 'david.wilding@canonical.com')
NHAN = ('Trong Nhan Mai', 'trongnhan.mai@canonical.com')
DEPENDABOT = ('dependabot[bot]', '49699333+dependabot[bot]@users.noreply.github.com')
PRINTS_CHARMING = ('Prints Charming', 'ben.hoyt+prints-charming-bot@canonical.com')
# Three shapes of contributor from outside the team, all observed in
# operator's history, and the reason `_authors` is not two lines long:
# Ali-932 and gcomneno commit under GitHub no-reply addresses, so a handle
# falls out of the email; Iya Mg does not, so there is no handle to be had
# and the name is the credit.
ALI = ('Ali Al-Obaidi', '46688206+Ali-932@users.noreply.github.com')
GCOMNENO = ('Giancarlo Cicellyn Comneno', '126195429+gcomneno@users.noreply.github.com')
IYA = ('Iya Mg', 'dev@iyamg.com')


def git_log(*commits: tuple[tuple[str, str], str, str]) -> str:
    """Build `GIT_LOG_FORMAT` text out of (author, subject, body) triples.

    This is what `git log --format="$(changelog git-log-format)"` would have
    written, assembled here so that a fixture can be read: the separators are
    control characters, and a checked-in file full of them is not reviewable.
    `test_the_fixture_format_is_the_format_git_is_asked_for` pins the two
    against each other so this cannot drift into testing a private dialect.
    """
    return ''.join(
        f'\x1e{name}\x1f{email}\x1f{subject}\x1f{body}' for (name, email), subject, body in commits
    )


# The same twenty-three pull requests as they appear in `git log --reverse
# 3.8.1..3.8.2`: author name, author email and squash-commit subject, all
# verbatim. This is the other end of the fixture above, and the pair is what
# `SameRangeFromEitherInputTests` compares.
OPERATOR_3_8_2_COMMITS = (
    (TONY, 'chore: adjust versions after release (#2670)', ''),
    (TONY, 'docs: give each best-practice admonition a stable :name: anchor (#2524)', ''),
    (TONY, 'ci: point DB charm CI at the moved mysql-operators repo (#2551)', ''),
    (DEPENDABOT, 'chore: bump cryptography from 48.0.1 to 50.0.0 (#2682)', ''),
    (ALI, 'fix: compare full event paths when skipping duplicate notices (#2684)', ''),
    (DEPENDABOT, 'chore: bump the actions group across 1 directory with 8 updates (#2674)', ''),
    (DEPENDABOT, 'chore: bump the runtime group across 1 directory with 4 updates (#2691)', ''),
    (TONY, 'docs: reword text that vale 3.17 flags as misspelled (#2695)', ''),
    (PRINTS_CHARMING, 'chore: update charm pins (#2582)', ''),
    (
        DEPENDABOT,
        'chore: bump the dev-tooling group in /examples/httpbin-demo with 2 updates (#2675)',
        '',
    ),
    (DEPENDABOT, 'chore: bump the charm-tech group across 1 directory with 3 updates (#2697)', ''),
    (TONY, 'docs: stop styling page references as blockquotes (#2666)', ''),
    (DAVID, 'ci: switch example charm integration tests to Concierge `k8s` preset (#2696)', ''),
    (TONY, 'docs: make the custom-endpoint-name sample test actually test something (#2664)', ''),
    (TONY, 'ci: use the upstream concierge presets again (#2699)', ''),
    (DAVID, 'docs: replace `requests` by `urllib` in K8s tutorial integration tests (#2687)', ''),
    (TONY, "fix: don't pass a message when converting an unknown status by name (#2700)", ''),
    (DEPENDABOT, 'chore: bump the dev-tooling group with 4 updates (#2676)', ''),
    (PRINTS_CHARMING, 'chore: update charm pins (#2701)', ''),
    (TONY, "chore: adopt ruff 0.16's new lint conventions (#2698)", ''),
    (TONY, 'docs: recommend spread directly, rather than charmcraft test (#2706)', ''),
    (
        NHAN,
        'docs: extract sections in how to write integration tests to their own howto'
        ' guide (#2662)',
        '',
    ),
    (DAVID, 'chore: update changelog and versions for 3.8.2 release (#2716)', ''),
)

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


# The same four pull requests as commits. Observed, and trimmed to the same
# four so that this pairs with the notes fixture above.
OPERATOR_BREAKING_COMMITS = (
    (TONY, 'refactor: replace jsonpatch with an inline dict-diff (#2578)', ''),
    (
        TONY,
        'refactor!: move the otlp-json package to be a regular ops-tracing module (#2585)',
        '',
    ),
    (TONY, 'feat: note the socket path in Pebble tracing spans (#2555)', ''),
    (TONY, 'fix: tear down `Runtime.exec()` when the charm raises (#2581)', ''),
)

# Six real commits from the 3.7.1..3.8.0 range, in merge order, chosen for
# what they carry rather than trimmed for length: the only revert operator
# has merged into a 3.x release (#2568) together with the pull request it
# reverts (#2538), and one of each shape of outside contributor. The body of
# #2568 is real too, down to the third line; every other body is elided.
#
# This range has no notes counterpart in these tests, deliberately. Two of
# the three contributors here have no handle in the git log at all, so the
# notes GitHub generated for 3.8.0 say something this fixture cannot be
# derived from, and inventing the handles would be inventing the answer to
# the question `AuthorCreditTests` asks.
OPERATOR_REVERT_RANGE_COMMITS = (
    (GCOMNENO, 'fix: treat remote unit zero as explicit (#2454)', ''),
    (IYA, 'docs: fix small issues in K8s tutorial (#2540)', ''),
    (TONY, 'docs: replace CoC with link to Ubuntu Code of Conduct (#2564)', ''),
    (DEPENDABOT, 'chore: bump opentelemetry-api from 1.37.0 to 1.42.1 (#2538)', ''),
    (
        TONY,
        'revert: "chore: bump opentelemetry-api from 1.37.0 to 1.42.1" (#2568)',
        'Reverts canonical/operator#2538\n\nTriggers warnings on 3.10.\n',
    ),
    (
        ('deusebio', 'edeusebio85@gmail.com'),
        'docs: add guidance about names of workload-less charms (#2496)',
        '',
    ),
)

OPERATOR_3_8_2_LOG = git_log(*OPERATOR_3_8_2_COMMITS)
OPERATOR_BREAKING_LOG = git_log(*OPERATOR_BREAKING_COMMITS)
OPERATOR_REVERT_RANGE_LOG = git_log(*OPERATOR_REVERT_RANGE_COMMITS)

#: `OPERATOR_TEAM` as a workflow would pass it: one repository variable.
TEAM_ARGUMENT = ','.join(OPERATOR_TEAM)


class RealReleaseTests(unittest.TestCase):
    """The 3.8.2 fixture, end to end."""

    #: A git log carries no compare link, so a caller that wants one supplies
    #: it. This is what `changelog release-notes --compare-url` takes.
    compare_url = 'https://github.com/canonical/operator/compare/3.8.1...3.8.2'

    def setUp(self):
        self.categories = parse_git_log(OPERATOR_3_8_2_LOG, team=OPERATOR_TEAM, repo=REPO)

    def test_categories(self):
        # Twelve of the twenty-three pull requests survive, in merge order.
        # Only #2684 carries a credit: its author is the one contributor in
        # this range who is not on the team.
        assert self.categories == {
            'breaking': [],
            'feat': [],
            'fix': [
                Change(
                    'Compare full event paths when skipping duplicate notices', 2684, '@Ali-932'
                ),
                Change("Don't pass a message when converting an unknown status by name", 2700),
            ],
            'docs': [
                Change('Give each best-practice admonition a stable :name: anchor', 2524),
                Change('Reword text that vale 3.17 flags as misspelled', 2695),
                Change('Stop styling page references as blockquotes', 2666),
                Change('Make the custom-endpoint-name sample test actually test something', 2664),
                Change('Replace `requests` by `urllib` in K8s tutorial integration tests', 2687),
                Change('Recommend spread directly, rather than charmcraft test', 2706),
                Change(
                    'Extract sections in how to write integration tests to their own howto guide',
                    2662,
                ),
            ],
            'test': [],
            'refactor': [],
            'perf': [],
            'ci': [
                Change('Point DB charm CI at the moved mysql-operators repo', 2551),
                Change('Switch example charm integration tests to Concierge `k8s` preset', 2696),
                Change('Use the upstream concierge presets again', 2699),
            ],
            'revert': [],
        }

    def test_chore_is_dropped(self):
        # Eleven of the twenty-three pull requests are `chore`, and none of
        # them reaches the output. Deliberate: dependency bumps, charm-pin
        # updates and the release's own version bump are not changelog
        # material.
        notes = format_release_notes(self.categories, self.compare_url, repo=REPO)
        entry = format_changes(self.categories, '3.8.2', datetime.date(2026, 8, 31))
        assert 'chore' not in notes.lower()
        assert 'chore' not in entry.lower()
        for pr in OPERATOR_3_8_2_CHORE_PRS:
            assert pr not in notes, f'chore PR #{pr} leaked into the release notes'
            assert pr not in entry, f'chore PR #{pr} leaked into the changelog entry'

    def test_new_contributors_section_is_dropped(self):
        notes = format_release_notes(self.categories, self.compare_url, repo=REPO)
        assert 'New Contributors' not in notes
        assert 'made their first contribution' not in notes

    def test_changes_entry(self):
        # This is the 3.8.2 entry as it appears in operator's CHANGES.md,
        # with two differences. Three summaries were edited by hand after
        # the fact (#2700 gained an "In `ops.testing`," prefix, #2524 lost
        # its ":name:", and #2662 was reworded). And #2684 is credited here
        # and was not there: the author is not on the team, `release.py`
        # discarded the author of every entry, and nobody put this one back
        # by hand -- which is the whole of the argument for doing it here.
        # The section order, the bullet order within each section and the
        # blank-line layout are all exactly what shipped.
        assert (
            format_changes(self.categories, '3.8.2', datetime.date(2026, 8, 31))
            == """\
# 3.8.2 - 31 August 2026

## Fixes

* Compare full event paths when skipping duplicate notices by @Ali-932 (#2684)
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
            format_release_notes(self.categories, self.compare_url, repo=REPO)
            == """\
## What's Changed

### Fixes
* Compare full event paths when skipping duplicate notices by @Ali-932 in https://github.com/canonical/operator/pull/2684
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

    #: Supplied by the caller, the way `--compare-url` does: see
    #: `RealReleaseTests`.
    compare_url = 'https://github.com/canonical/operator/compare/3.7.1...3.8.0'

    def setUp(self):
        self.categories = parse_git_log(OPERATOR_BREAKING_LOG, team=OPERATOR_TEAM, repo=REPO)

    def test_breaking_entry_keeps_its_real_type_as_a_prefix(self):
        assert self.categories['breaking'] == [
            Change('Refactor: Move the otlp-json package to be a regular ops-tracing module', 2585)
        ]

    def test_breaking_entry_is_not_also_in_its_own_type(self):
        # The `!` moves the entry rather than copying it, so #2585 leaves
        # `refactor` and #2578, which has no `!`, is all that is left there.
        assert self.categories['refactor'] == [
            Change('Replace jsonpatch with an inline dict-diff', 2578)
        ]

    def test_release_notes_put_breaking_first_with_a_warning(self):
        assert (
            format_release_notes(self.categories, self.compare_url, repo=REPO)
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


class FormatReleaseNotesTests(unittest.TestCase):
    def empty(self) -> dict[str, list[Change]]:
        return {category: [] for category in CATEGORIES}

    def test_empty_release(self):
        assert format_release_notes(self.empty(), None, repo=REPO) == "## What's Changed\n"

    def test_categories_render_in_the_declared_order(self):
        categories = self.empty()
        for category in ('revert', 'ci', 'feat', 'fix'):
            categories[category] = [Change(f'A {category} change', 1)]
        headings = [
            line
            for line in format_release_notes(categories, None, repo=REPO).splitlines()
            if line.startswith('###')
        ]
        assert headings == ['### Features', '### Fixes', '### CI', '### Reverted']

    def test_the_compare_url_becomes_the_closing_line(self):
        # The caller passes the link; the prefix is the package's, so that
        # notes rendered here read the same as notes rendered by GitHub.
        notes = format_release_notes(self.empty(), 'https://example.com/x', repo=REPO)
        assert notes.endswith('**Full Changelog**: https://example.com/x')


class FormatChangesTests(unittest.TestCase):
    def entry(self, change: Change) -> str:
        categories: dict[str, list[Change]] = {category: [] for category in CATEGORIES}
        categories['fix'] = [change]
        return format_changes(categories, '1.2.3', datetime.date(2026, 9, 10))

    def test_the_pr_number_is_rendered_in_parentheses(self):
        assert '* A fix (#2684)' in self.entry(Change('A fix', 2684))

    def test_a_change_with_no_pr_gets_no_reference(self):
        # A commit pushed straight to the branch has no pull request, and is
        # still a change that shipped. It is listed with nothing after it
        # rather than with a placeholder: a reader can act on "there is no
        # pull request for this", where a question mark only reads as
        # something having gone wrong.
        assert self.entry(Change('A fix')).endswith('* A fix\n\n')

    def test_the_credit_goes_before_the_reference(self):
        # `* <what> by <who> (#<where>)`, which is the shape operator's own
        # hand-written entries use: `* Fix typos in code snippets by
        # @MattiaSarti (#1750)`.
        assert '* A fix by @someone (#2684)' in self.entry(Change('A fix', 2684, '@someone'))

    def test_a_credited_change_with_no_pr_keeps_the_credit(self):
        assert self.entry(Change('A fix', None, 'Iya Mg')).endswith('* A fix by Iya Mg\n\n')

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


# The `chore` half of the 3.8.2 fixture on its own: eleven real pull requests,
# nothing else. A release with nothing in it but dependency bumps and charm
# pins is not hypothetical, and it is a patch.
OPERATOR_CHORE_ONLY_LOG = git_log(
    *(commit for commit in OPERATOR_3_8_2_COMMITS if commit[1].startswith('chore'))
)

# The one `!` pull request operator has merged into a 3.x release, by itself.
# The rest of the 3.7.1..3.8.0 range is what makes that release obviously a
# minor one; without it, the `!` has to carry the decision alone.
OPERATOR_BREAKING_ONLY_LOG = git_log((
    TONY,
    'refactor!: move the otlp-json package to be a regular ops-tracing module (#2585)',
    '',
))


def categories_of(log: str) -> dict[str, list[Change]]:
    return parse_git_log(log, team=OPERATOR_TEAM, repo=REPO)


class BumpSizeTests(unittest.TestCase):
    """The rule -- a `feat` in the range means minor, otherwise patch -- against real releases."""

    def test_a_release_with_no_features_is_a_patch(self):
        # 3.8.1 -> 3.8.2: two fixes, seven docs, three CI, eleven chore. It
        # shipped as a patch.
        assert infer_bump_size(categories_of(OPERATOR_3_8_2_LOG)) == PATCH

    def test_a_release_with_a_feature_is_a_minor(self):
        # 3.7.1 -> 3.8.0, trimmed: one `feat` (#2555) among four pull
        # requests. It shipped as a minor.
        assert infer_bump_size(categories_of(OPERATOR_BREAKING_LOG)) == MINOR

    def test_a_breaking_change_on_its_own_is_a_minor(self):
        # #2585 is a `refactor!`, so on the plain reading of the rule -- "a
        # `feat` in the range means minor" -- a release containing only it
        # would be a patch, and a breaking change would ship in a patch
        # release. A `!` does not infer a major bump, because we have decided
        # to let a breaking change ride in a minor when the impact has been
        # checked. Riding in a patch is not the same decision, and is not one
        # anyone has made. So a `!` means at least minor.
        assert infer_bump_size(categories_of(OPERATOR_BREAKING_ONLY_LOG)) == MINOR

    def test_a_breaking_feature_is_still_a_minor(self):
        # The regression this guards against: parsing *moves* a `!` entry out
        # of its real type, so a range whose only feature is a `feat!` has an
        # empty `feat` list. A rule that read `feat` alone would call this a
        # patch. operator has not merged a `feat!` into a 3.x release, so this
        # commit is made up rather than lifted.
        categories = categories_of(git_log((TONY, 'feat!: replace the framework API (#1)', '')))
        assert categories['feat'] == []
        assert infer_bump_size(categories) == MINOR

    def test_a_release_of_nothing_but_chores_is_a_patch(self):
        assert infer_bump_size(categories_of(OPERATOR_CHORE_ONLY_LOG)) == PATCH

    def test_an_empty_range_is_a_patch(self):
        assert infer_bump_size(categories_of('')) == PATCH

    def test_major_is_never_inferred(self):
        # Even with every category populated, including breaking. A major
        # release is the explicit version input's job.
        categories = {category: [Change(f'A {category} change', 1)] for category in CATEGORIES}
        assert infer_bump_size(categories) == MINOR

    def test_the_minor_categories_are_categories(self):
        # Otherwise this would be a second type list quietly diverging from
        # the first: a renamed category would stop being a minor bump without
        # anything saying so.
        assert set(MINOR_BUMP_CATEGORIES) <= set(CATEGORIES)


class NextVersionTests(unittest.TestCase):
    """Applying a size to a version. Generic semver, and nothing beyond it."""

    def test_real_history(self):
        # The two releases the fixtures above are taken from.
        assert next_version(previous='3.7.1', size=MINOR) == '3.8.0'
        assert next_version(previous='3.8.1', size=PATCH) == '3.8.2'

    def test_a_minor_bump_zeroes_the_patch(self):
        assert next_version(previous='3.8.2', size=MINOR) == '3.9.0'

    def test_components_are_numbers_not_digits(self):
        assert next_version(previous='3.9.9', size=PATCH) == '3.9.10'
        assert next_version(previous='2.23.16', size=PATCH) == '2.23.17'
        assert next_version(previous='3.9.1', size=MINOR) == '3.10.0'

    def test_surrounding_whitespace_is_tolerated(self):
        # `--previous "$(git describe --tags --abbrev=0)"` arrives with a
        # newline on it often enough to be worth not failing over.
        assert next_version(previous=' 3.8.1\n', size=PATCH) == '3.8.2'

    def test_a_dev_version_is_rejected(self):
        # The one that matters. Between releases `ops/version.py` holds
        # something like 3.9.0.dev0, and reaching for it as the previous
        # version is the easy mistake: it is a guess made by the last
        # post-release bump, not a version that was ever released. Bumping it
        # would skip a version, and stripping the suffix silently would
        # release whatever that guess happened to be.
        with self.assertRaises(ValueError):
            next_version(previous='3.9.0.dev0', size=MINOR)

    def test_a_pre_release_is_rejected(self):
        for version in ('3.8.0b1', '3.8.0rc1', '3.8.0a1'):
            with self.assertRaises(ValueError):
                next_version(previous=version, size=MINOR)

    def test_a_tag_that_is_not_a_version_is_rejected(self):
        for previous in ('v3.8.1', '3.8', '', 'main'):
            with self.assertRaises(ValueError):
                next_version(previous=previous, size=PATCH)

    def test_an_unknown_size_is_rejected(self):
        # Including 'major', which is not a size this package produces.
        with self.assertRaises(ValueError):
            next_version(previous='3.8.1', size='major')  # type: ignore[arg-type]

    def test_the_error_points_at_the_way_out(self):
        with self.assertRaises(ValueError) as raised:
            next_version(previous='3.9.0.dev0', size=MINOR)
        assert 'explicitly' in str(raised.exception)


class GitLogParseTests(unittest.TestCase):
    """The primary input: commit subjects, which is what the convention governs."""

    def parse(self, *commits: tuple[tuple[str, str], str, str]) -> dict[str, list[Change]]:
        return parse_git_log(git_log(*commits), team=OPERATOR_TEAM, repo=REPO)

    def test_the_fixture_format_is_the_format_git_is_asked_for(self):
        # `git_log` writes the separators by hand, so if the package ever
        # changed what it asks `git log` for, these fixtures would go on
        # passing while every real caller broke. The format string is the
        # contract; this is the only place it is checked against the fixtures.
        assert GIT_LOG_FORMAT == '%x1e%an%x1f%ae%x1f%s%x1f%b'

    def test_the_real_release(self):
        categories = parse_git_log(OPERATOR_3_8_2_LOG, team=OPERATOR_TEAM, repo=REPO)
        assert categories['fix'] == [
            Change('Compare full event paths when skipping duplicate notices', 2684, '@Ali-932'),
            Change("Don't pass a message when converting an unknown status by name", 2700),
        ]
        assert categories['ci'] == [
            Change('Point DB charm CI at the moved mysql-operators repo', 2551),
            Change('Switch example charm integration tests to Concierge `k8s` preset', 2696),
            Change('Use the upstream concierge presets again', 2699),
        ]

    def test_the_pr_number_comes_off_the_subject(self):
        # The `(#N)` a squash merge appends, and the only thing the git log
        # says about the pull request. Over operator's last 300 commits every
        # subject has one.
        categories = self.parse((TONY, 'fix: do the thing (#1234)', ''))
        assert categories['fix'] == [Change('Do the thing', 1234)]

    def test_a_commit_with_no_pr_number_carries_none(self):
        # A commit pushed straight to the branch. operator has these, from
        # before the squash-merge policy -- `chore: remove odd argument to
        # "raise NotImplementedError" in harness.py` is one, by Ben, with no
        # suffix. The change is real, so it is carried with nothing in the
        # number rather than with a placeholder that reads like a bug.
        categories = self.parse((TONY, 'fix: do the thing', ''))
        assert categories['fix'] == [Change('Do the thing', None)]

    def test_a_number_that_is_not_the_suffix_is_not_the_pr(self):
        # Only a trailing `(#N)` counts, so a summary that happens to mention
        # an issue does not get mistaken for one.
        categories = self.parse((TONY, 'fix: handle (#5) style input properly (#1234)', ''))
        assert categories['fix'] == [Change('Handle (#5) style input properly', 1234)]

    def test_chore_is_dropped_here_too(self):
        categories = self.parse((TONY, 'chore: bump something (#1)', ''))
        assert all(not items for items in categories.values())

    def test_a_breaking_commit_moves_to_breaking_with_its_type_kept(self):
        categories = self.parse((TONY, 'refactor!: move the thing (#2585)', ''))
        assert categories['breaking'] == [Change('Refactor: Move the thing', 2585)]
        assert categories['refactor'] == []

    def test_a_scope_is_accepted_and_ignored(self):
        # No repository in the estate uses one, but the shared PR-title check
        # accepts `type(scope):`, and the two should not disagree about what
        # a valid subject is.
        categories = self.parse((TONY, 'fix(tracing): do the thing (#1)', ''))
        assert categories['fix'] == [Change('Do the thing', 1)]

    def test_a_breaking_scoped_commit_is_still_breaking(self):
        categories = self.parse((TONY, 'feat(api)!: replace it (#1)', ''))
        assert categories['breaking'] == [Change('Feat: Replace it', 1)]

    def test_a_subject_that_is_not_conventional_is_dropped(self):
        # A merge commit, or anything from before the convention. `--no-merges`
        # is the recommendation rather than the requirement because of this.
        categories = self.parse(
            (TONY, "Merge remote-tracking branch 'source/main' into import-ops-scenario", ''),
            (TONY, 'Reorganise the scenario files.', ''),
            (TONY, 'fix: a real one (#1)', ''),
        )
        assert categories['fix'] == [Change('A real one', 1)]
        assert sum(len(items) for items in categories.values()) == 1

    def test_a_body_does_not_end_a_record(self):
        # The reason the format uses control characters: a commit body is
        # arbitrary text with blank lines in it, so anything line-oriented
        # would lose track of where the next commit starts.
        categories = self.parse(
            (TONY, 'fix: the first (#1)', 'A body.\n\nWith a blank line.\n\n* And a bullet.\n'),
            (TONY, 'fix: the second (#2)', ''),
        )
        assert categories['fix'] == [Change('The first', 1), Change('The second', 2)]

    def test_an_empty_log_is_every_category_empty(self):
        assert parse_git_log('') == {category: [] for category in CATEGORIES}

    def test_trailing_whitespace_between_records_is_tolerated(self):
        # `git log` output arrives with a newline on the end of it.
        categories = parse_git_log(
            git_log((TONY, 'fix: do the thing (#1)', '')) + '\n', team=OPERATOR_TEAM
        )
        assert categories['fix'] == [Change('Do the thing', 1)]


class AuthorCreditTests(unittest.TestCase):
    """Who gets named in a bullet. All three contributors here are observed."""

    def parse(self, author: tuple[str, str], team=OPERATOR_TEAM) -> list[Change]:
        return parse_git_log(git_log((author, 'fix: do the thing (#1)', '')), team=team)['fix']

    def test_a_team_member_is_not_credited(self):
        # By email, which is all a git log gives for someone who commits
        # under a real address.
        assert self.parse(TONY) == [Change('Do the thing', 1)]

    def test_an_outside_contributor_is_credited_by_handle(self):
        # `46688206+Ali-932@users.noreply.github.com` -> `@Ali-932`. This is
        # GitHub's default commit address for an account with a private
        # email, so it is the usual case for a drive-by contributor.
        assert self.parse(ALI) == [Change('Do the thing', 1, '@Ali-932')]

    def test_the_older_no_reply_form_works_too(self):
        assert self.parse(('Someone', 'someone@users.noreply.github.com')) == [
            Change('Do the thing', 1, '@someone')
        ]

    def test_an_outside_contributor_with_no_handle_is_credited_by_name(self):
        # Iya Mg's #2540 is a real documentation fix in 3.8.0, committed from
        # a personal address. There is no handle to be had, and the two
        # alternatives -- dropping them, or rendering an `@` in front of
        # something that is not a handle -- are both worse than the name.
        assert self.parse(IYA) == [Change('Do the thing', 1, 'Iya Mg')]

    def test_another_canonical_team_is_still_outside_this_one(self):
        # "External to the Charm Tech team" is not "external to Canonical".
        # A contributor from another team has an @canonical.com address, no
        # derivable handle, and every bit as much claim to the credit.
        assert self.parse(('Some One', 'some.one@canonical.com')) == [
            Change('Do the thing', 1, 'Some One')
        ]

    def test_a_team_member_is_matched_by_handle_as_well_as_by_email(self):
        # Someone on the team who commits from a no-reply address is matched
        # on the handle the email yields, so a team list of handles alone
        # still works.
        assert self.parse(
            ('Tony Meyer', '12345+tonyandrewmeyer@users.noreply.github.com'),
            team=('@tonyandrewmeyer',),
        ) == [Change('Do the thing', 1)]

    def test_matching_ignores_case_and_a_leading_at(self):
        for member in ('TONY.MEYER@CANONICAL.COM', 'tony.meyer@canonical.com'):
            assert self.parse(TONY, team=(member,)) == [Change('Do the thing', 1)], member
        no_reply = ('Tony Meyer', '12345+tonyandrewmeyer@users.noreply.github.com')
        for member in ('@TONYANDREWMEYER', 'tonyandrewmeyer', '@tonyandrewmeyer'):
            assert self.parse(no_reply, team=(member,)) == [Change('Do the thing', 1)], member

    def test_a_handle_in_the_team_does_not_match_an_author_who_has_no_handle(self):
        # Not a bug, and worth pinning: nothing in a git log connects
        # `tony.meyer@canonical.com` to `@tonyandrewmeyer`. A team list of
        # handles alone covers only the members who commit from a GitHub
        # no-reply address, which is why `OPERATOR_TEAM` carries both.
        assert self.parse(TONY, team=('@tonyandrewmeyer',)) == [
            Change('Do the thing', 1, 'Tony Meyer')
        ]

    def test_an_empty_team_credits_everyone(self):
        # The safe failure. A repository that has not said who maintains it
        # over-credits, which is visible in the draft release and takes one
        # edit; the other way round, a contributor is silently left out.
        assert self.parse(TONY, team=()) == [Change('Do the thing', 1, 'Tony Meyer')]


class RevertTests(unittest.TestCase):
    """Reverts.

    Working out whether a revert cancels something needs the revert commit's
    *body*, which is why the parser reads whole log records rather than
    subjects alone.

    Only the first case here is observed. operator has merged exactly one
    revert into a 3.x release -- #2568, reverting #2538 -- and it reverts a
    `chore`, which the changelog drops anyway, so the cancelling is real but
    the cancellation is not what makes it invisible. Every other fixture in
    this class is constructed: there is no instance in recent history of a
    revert of something in the changelog, and none at all of a revert of a
    released feature.
    """

    def parse(self, *commits: tuple[tuple[str, str], str, str]) -> dict[str, list[Change]]:
        return parse_git_log(git_log(*commits), team=OPERATOR_TEAM, repo=REPO)

    def test_the_real_revert_range(self):
        # Observed: six commits from 3.7.1..3.8.0. #2538 and #2568 cancel,
        # and neither is in the output -- though both are `chore`, so both
        # would have been dropped regardless.
        categories = self.parse(*OPERATOR_REVERT_RANGE_COMMITS)
        assert categories['revert'] == []
        assert categories['fix'] == [
            Change('Treat remote unit zero as explicit', 2454, '@gcomneno')
        ]
        assert categories['docs'] == [
            Change('Fix small issues in K8s tutorial', 2540, 'Iya Mg'),
            Change('Replace CoC with link to Ubuntu Code of Conduct', 2564),
            Change('Add guidance about names of workload-less charms', 2496, 'deusebio'),
        ]

    def test_a_revert_within_the_range_cancels_both_halves(self):
        # Constructed: a revert of a `fix` in the same range, which has no
        # instance in operator's recent history. A change that landed and was
        # taken out again before anything shipped did not happen as far as a
        # reader is concerned, so listing either half would be describing
        # something that never reached anyone.
        categories = self.parse(
            (TONY, 'fix: do the thing (#100)', ''),
            (TONY, 'fix: do the other thing (#101)', ''),
            (TONY, 'revert: "fix: do the thing" (#102)', 'Reverts canonical/operator#100\n'),
        )
        assert categories['fix'] == [Change('Do the other thing', 101)]
        assert categories['revert'] == []
        assert categories['breaking'] == []

    def test_a_revert_of_something_released_is_called_out(self):
        # Constructed. #99 is not in this range, so it shipped: the reader
        # needs to be told it has been taken back out. It keeps its own
        # `Reverted` heading rather than being filed under the `fix` it
        # undoes, which would read as a new fix rather than as a removal.
        categories = self.parse(
            (TONY, 'revert: "fix: do the thing" (#102)', 'Reverts canonical/operator#99\n'),
        )
        assert categories['revert'] == [Change('"fix: do the thing"', 102)]
        assert categories['fix'] == []

    def test_a_revert_of_something_released_is_at_least_a_patch(self):
        categories = self.parse(
            (TONY, 'revert: "fix: do the thing" (#102)', 'Reverts canonical/operator#99\n'),
        )
        assert infer_bump_size(categories) == PATCH

    def test_a_revert_of_a_released_feature_is_breaking(self):
        # Constructed, and the decision worth arguing with: taking away a
        # feature people may already be building on is a removal of
        # behaviour, whatever the commit type on the revert says. So it goes
        # to `breaking`, which is both the loudest heading and -- via
        # `MINOR_BUMP_CATEGORIES` -- a minor bump rather than a patch.
        categories = self.parse(
            (TONY, 'revert: "feat: add the thing" (#102)', 'Reverts canonical/operator#99\n'),
        )
        assert categories['breaking'] == [Change('Revert: "feat: add the thing"', 102)]
        assert categories['revert'] == []
        assert infer_bump_size(categories) == MINOR

    def test_a_revert_of_a_released_breaking_change_is_breaking(self):
        categories = self.parse(
            (TONY, 'revert: "refactor!: move it" (#102)', 'Reverts canonical/operator#99\n'),
        )
        assert categories['breaking'] == [Change('Revert: "refactor!: move it"', 102)]

    def test_a_revert_of_a_released_feature_in_range_still_cancels(self):
        # The cancelling comes first: a feature that never shipped cannot be
        # a breaking removal of anything.
        categories = self.parse(
            (TONY, 'feat: add the thing (#99)', ''),
            (TONY, 'revert: "feat: add the thing" (#102)', 'Reverts canonical/operator#99\n'),
        )
        assert categories['breaking'] == []
        assert categories['feat'] == []
        assert infer_bump_size(categories) == PATCH

    def test_an_unquoted_reverts_line_is_read(self):
        # GitHub's Revert button writes `Reverts owner/repo#N`, but a
        # hand-written revert often leaves the owner/repo off.
        categories = self.parse(
            (TONY, 'fix: do the thing (#100)', ''),
            (TONY, 'revert: "fix: do the thing" (#102)', 'Reverts #100\n'),
        )
        assert categories['fix'] == []
        assert categories['revert'] == []

    def test_a_reverts_line_naming_another_repository_is_ignored(self):
        # Otherwise `Reverts some/other#100` would cancel this repository's
        # #100, which has nothing to do with it.
        categories = self.parse(
            (TONY, 'fix: do the thing (#100)', ''),
            (TONY, 'revert: "fix: something else" (#102)', 'Reverts some/other#100\n'),
        )
        assert categories['fix'] == [Change('Do the thing', 100)]
        assert categories['revert'] == [Change('"fix: something else"', 102)]

    def test_a_revert_with_no_reverts_line_is_called_out(self):
        # Nothing says what it undoes, so there is nothing to cancel it
        # against. Showing it is the safe answer: the alternative is hiding a
        # change that shipped.
        categories = self.parse((TONY, 'revert: "fix: do the thing" (#102)', 'No idea.\n'))
        assert categories['revert'] == [Change('"fix: do the thing"', 102)]

    def test_a_revert_of_a_chore_is_still_dropped_when_called_out(self):
        # `revert` is a category and `chore` is not, so a revert of a chore
        # that is *not* cancelled still appears. That is the right way round:
        # the type of the thing reverted does not decide whether a revert is
        # worth reporting, because the reader is being told about the removal
        # rather than about the original.
        categories = self.parse(
            (TONY, 'revert: "chore: bump it" (#102)', 'Reverts canonical/operator#99\n'),
        )
        assert categories['revert'] == [Change('"chore: bump it"', 102)]


class ConsoleScriptTests(unittest.TestCase):
    """The `changelog` console script: a range on stdin, one answer on stdout."""

    def run_cli(self, *argv: str, stdin: str = OPERATOR_3_8_2_LOG) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            mock.patch('sys.stdin', io.StringIO(stdin)),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            returncode = _cli.main(argv)
        return returncode, out.getvalue(), err.getvalue()

    def test_bump_size_prints_one_bare_word(self):
        # `SIZE=$(changelog bump-size < log.txt)` is the whole of the
        # plumbing, so anything else on stdout -- a label, a prefix, JSON --
        # would have to be stripped back off in the workflow.
        assert self.run_cli('bump-size') == (0, 'patch\n', '')
        assert self.run_cli('bump-size', stdin=OPERATOR_BREAKING_LOG) == (0, 'minor\n', '')

    def test_next_version_prints_one_bare_word(self):
        assert self.run_cli('next-version', '--previous', '3.8.1') == (0, '3.8.2\n', '')
        minor = self.run_cli('next-version', '--previous', '3.7.1', stdin=OPERATOR_BREAKING_LOG)
        assert minor == (0, '3.8.0\n', '')

    def test_next_version_fails_rather_than_guessing(self):
        returncode, out, err = self.run_cli('next-version', '--previous', '3.9.0.dev0')
        assert returncode == 2
        # Nothing on stdout: a workflow capturing this into a variable gets
        # an empty one and a non-zero step, not a plausible wrong version.
        assert out == ''
        assert '3.9.0.dev0' in err

    def test_release_notes_is_the_library_output(self):
        categories = parse_git_log(OPERATOR_3_8_2_LOG, team=OPERATOR_TEAM, repo=REPO)
        _, out, _ = self.run_cli('release-notes', '--repo', REPO, '--team', TEAM_ARGUMENT)
        # No newline is added here, because the library's last line is the
        # blank one after the final category. With a compare link at the end
        # there is no trailing blank line, and `_emit` adds one; the
        # release-notes-input case below is that one.
        assert out == format_release_notes(categories, None, repo=REPO)
        assert out.endswith('/pull/2699\n')

    def test_release_notes_needs_a_repo_to_build_links_from(self):
        # A change carries a number, not a URL, so there is nothing to render
        # a link out of without this. Failing is better than printing a body
        # whose every bullet has quietly lost its link.
        with self.assertRaises(SystemExit):
            self.run_cli('release-notes')

    def test_release_notes_takes_a_compare_link_it_cannot_work_out(self):
        # A git log has no equivalent of the line GitHub's generated notes
        # end with, and the tags at either end of the range are the caller's
        # to know, so this is how a workflow keeps the link.
        url = 'https://github.com/canonical/operator/compare/3.8.1...3.8.2'
        _, out, _ = self.run_cli('release-notes', '--repo', REPO, '--compare-url', url)
        assert out.endswith(f'**Full Changelog**: {url}\n')

    def test_release_notes_has_no_compare_link_by_default(self):
        _, out, _ = self.run_cli('release-notes', '--repo', REPO)
        assert 'Full Changelog' not in out

    def test_changes_entry_is_the_library_output_byte_for_byte(self):
        categories = parse_git_log(OPERATOR_3_8_2_LOG, team=OPERATOR_TEAM)
        _, out, _ = self.run_cli(
            'changes-entry', '--tag', '3.8.2', '--date', '2026-08-31', '--team', TEAM_ARGUMENT
        )
        # Including the blank line it ends with: this text is prepended to
        # CHANGES.md verbatim, so the trailing layout is part of the answer.
        assert out == format_changes(categories, '3.8.2', datetime.date(2026, 8, 31))
        assert out.endswith('(#2699)\n\n')

    def test_changes_entry_needs_no_repo(self):
        # It renders `(#2684)` and never a URL, so unlike `release-notes` it
        # has nothing to build out of a repository name.
        returncode, out, _ = self.run_cli(
            'changes-entry', '--tag', '3.8.2', '--date', '2026-08-31'
        )
        assert returncode == 0
        assert '(#2684)' in out

    def test_the_team_is_comma_separated_and_repeatable(self):
        # A workflow passes one repository variable with commas in it; a
        # person types one `--team` per person. Both, and a mixture.
        # A handle rather than an email, because it has to suppress the
        # credit on both input paths and only the git log has an email to
        # match: see `test_an_email_cannot_match_an_author_the_notes_name`.
        ali = '@Ali-932'
        for argv in (
            ('--team', f'{TEAM_ARGUMENT},{ali}'),
            ('--team', TEAM_ARGUMENT, '--team', ali),
            ('--team', TEAM_ARGUMENT, '--team', f'someone@example.com,{ali}'),
        ):
            _, out, _ = self.run_cli(
                'changes-entry', '--tag', '3.8.2', '--date', '2026-08-31', *argv
            )
            # Everyone in this range is now accounted for, so the one
            # bullet that was credited no longer is.
            uncredited = '* Compare full event paths when skipping duplicate notices (#2684)'
            assert uncredited in out, argv
            assert '@Ali-932' not in out, argv

    def test_without_a_team_everyone_is_credited(self):
        # The safe way round: over-crediting shows up in the draft release
        # and takes one edit, while crediting nobody is invisible. Note that
        # Tony is credited by *name* here: he commits from an @canonical.com
        # address, so the git log has no handle for him.
        _, out, _ = self.run_cli('changes-entry', '--tag', '3.8.2', '--date', '2026-08-31')
        assert (
            '* Compare full event paths when skipping duplicate notices by @Ali-932 (#2684)' in out
        )
        assert '* Stop styling page references as blockquotes by Tony Meyer (#2666)' in out

    def test_changes_entry_defaults_to_today(self):
        with mock.patch.object(_cli, '_today', return_value=datetime.date(2026, 9, 11)):
            _, out, _ = self.run_cli('changes-entry', '--tag', '3.8.2')
        assert out.startswith('# 3.8.2 - 11 September 2026\n')

    def test_git_log_format_prints_the_format_and_reads_nothing(self):
        # The one subcommand that does not touch stdin. It exists so that the
        # separators live in one place: a workflow that retypes them and drops
        # one gets an empty changelog rather than an error.
        assert self.run_cli('git-log-format', stdin='') == (0, GIT_LOG_FORMAT + '\n', '')

    def test_the_clock_is_read_here_and_only_here(self):
        # The `no_clock` fixture is active for this test, as it is for every
        # other, and `_cli` is deliberately outside it. If this starts
        # failing, the boundary has moved: something in the library is
        # reading the clock, or `_today` has been moved in with it.
        assert isinstance(_cli._today(), datetime.date)

    def test_an_unparseable_date_is_rejected(self):
        with self.assertRaises(SystemExit):
            self.run_cli('changes-entry', '--tag', '3.8.2', '--date', 'yesterday')

    def test_a_subcommand_is_required(self):
        with self.assertRaises(SystemExit):
            self.run_cli()

    def test_the_entry_point_names_something_that_exists(self):
        # A renamed `main` breaks the console script without breaking a
        # single test that calls `_cli.main` directly, so pin the string in
        # pyproject.toml against the module.
        pyproject = (pathlib.Path(__file__).parent.parent / 'pyproject.toml').read_text()
        assert 'changelog = "charm_tech_code.changelog._cli:main"' in pyproject
        assert callable(_cli.main)
