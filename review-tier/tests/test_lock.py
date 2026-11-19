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


"""The `uv.lock` comparison: where a dependency change in a release PR would hide."""

from __future__ import annotations

import pytest
from conftest import fixture

from charm_tech_code.review_tier._tiers import lock_differences

OWN = frozenset({'ops', 'ops-scenario', 'ops-tracing'})
# The real base and head of canonical/operator#2807 (after the 3.9.0 release),
# trimmed to the packages the tests touch.
BASE = fixture('uv-2807-base.lock')
HEAD = fixture('uv-2807-head.lock')


def mutate(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def test_real_post_release_lock_passes():
    assert BASE != HEAD
    assert lock_differences(BASE, HEAD, OWN) == []


def test_own_versions_and_pins_may_change():
    head = mutate(
        HEAD,
        '{ name = "ops", editable = "." },\n    { name = "pyyaml"',
        '{ name = "ops", specifier = "==3.10.0.dev0", editable = "." },\n    { name = "pyyaml"',
    )
    head = mutate(
        head,
        'name = "ops-tracing"\nversion = "3.10.0.dev0"',
        'name = "ops-tracing"\nversion = "4.0.0"',
    )
    assert lock_differences(BASE, head, OWN) == []


def test_reordering_and_reformatting_are_not_changes():
    head = HEAD.replace('{ name = "pyyaml" }', '{name="pyyaml"}')
    head = mutate(head, 'version = 1\nrevision = 5\n', 'revision = 5\nversion = 1\n')
    assert lock_differences(BASE, head, OWN) == []


def test_reordered_string_list_is_not_a_change():
    # canonical/operator#2806: a newer uv wrote ops's extras in another order.
    head = mutate(
        HEAD,
        'provides-extras = ["harness", "testing", "tracing"]',
        'provides-extras = ["testing", "harness", "tracing"]',
    )
    assert lock_differences(BASE, head, OWN) == []


def test_string_list_entry_added():
    head = mutate(
        HEAD,
        'provides-extras = ["harness", "testing", "tracing"]',
        'provides-extras = ["harness", "testing", "tracing", "extra"]',
    )
    assert lock_differences(BASE, head, OWN) == ['package[ops].metadata.provides-extras changed']


def test_hidden_dependency_added_to_our_package():
    head = mutate(
        HEAD,
        'dependencies = [\n    { name = "opentelemetry-api" },\n    { name = "pyyaml" },',
        'dependencies = [\n    { name = "opentelemetry-api" },\n    { name = "pyyaml" },\n'
        '    { name = "requests" },',
    )
    diffs = lock_differences(BASE, head, OWN)
    assert diffs == ['package[ops].dependencies: requests added']


def test_hidden_package_added():
    head = HEAD + '\n[[package]]\nname = "evil"\nversion = "1.0"\nsource = { registry = "x" }\n'
    assert lock_differences(BASE, head, OWN) == ['package: evil 1.0 added']


def test_dependency_removed():
    head = mutate(
        HEAD,
        'dependencies = [\n    { name = "opentelemetry-api" },\n    { name = "pyyaml" },\n'
        '    { name = "websocket-client" },',
        'dependencies = [\n    { name = "opentelemetry-api" },\n    { name = "pyyaml" },',
    )
    assert lock_differences(BASE, head, OWN) == [
        'package[ops].dependencies: websocket-client removed'
    ]


def test_package_removed():
    start = HEAD.index('[[package]]\nname = "websocket-client"')
    assert lock_differences(BASE, HEAD[:start], OWN) == ['package: websocket-client 1.9.2 removed']


def test_dependency_repinned():
    head = mutate(HEAD, 'name = "pyyaml"\nversion = "6.0.3"', 'name = "pyyaml"\nversion = "6.0.2"')
    diffs = lock_differences(BASE, head, OWN)
    assert 'package: pyyaml 6.0.2 added' in diffs
    assert 'package: pyyaml 6.0.3 removed' in diffs


def test_requirement_specifier_changed():
    head = mutate(
        HEAD, '{ name = "pyyaml", specifier = "==6.*" }', '{ name = "pyyaml", specifier = ">=5" }'
    )
    assert lock_differences(BASE, head, OWN) == [
        'package[ops].metadata.requires-dist[pyyaml].specifier changed'
    ]


def test_marker_dropped_from_our_requirement():
    head = mutate(
        HEAD,
        '{ name = "ops-tracing", marker = "extra == \'tracing\'", editable = "tracing" }',
        '{ name = "ops-tracing", editable = "tracing" }',
    )
    diffs = lock_differences(BASE, head, OWN)
    assert diffs == ['package[ops].metadata.requires-dist[ops-tracing].marker removed']


def test_our_package_moved_to_a_registry():
    head = mutate(
        HEAD,
        'name = "ops-tracing"\nversion = "3.10.0.dev0"\nsource = { editable = "tracing" }',
        'name = "ops-tracing"\nversion = "3.10.0"\nsource = { registry = "https://example.org" }',
    )
    assert lock_differences(BASE, head, OWN) == [
        'package[ops-tracing].source.editable removed',
        'package[ops-tracing].source.registry added',
    ]


def test_lock_header_change():
    # 3.9.0's release-prep PR (#2806) re-locked with a newer uv, which bumped this.
    head = mutate(HEAD, 'revision = 5\n', 'revision = 6\n')
    assert lock_differences(BASE, head, OWN) == ['revision changed']


@pytest.mark.parametrize('name', ['ops-scenario', 'ops-tracing'])
def test_other_packages_versions_are_not_ours(name):
    # A third-party package called, say, 'ops-tracing-extra' is not ours.
    head = mutate(HEAD, f'name = "{name}"\n', f'name = "{name}-extra"\n')
    assert lock_differences(BASE, head, OWN)
