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


"""Unit tests for draft-release-notes."""

from __future__ import annotations

import io
import json
import pathlib
import re
import urllib.error
import urllib.request
from unittest import mock

import pytest

from charm_tech_code.draft_release_notes import _cli
from charm_tech_code.draft_release_notes._draft import (
    placeholder,
    system_prompt,
    tidy,
    user_prompt,
)
from charm_tech_code.draft_release_notes._openrouter import error_detail

CHANGELOG = """# 3.8.3 - 22 September 2026

## Fixes

* Stop the kettle reporting itself boiled while cold ([#101](https://example.com/101))
"""


class _Response(io.BytesIO):
    """Stands in for what `urlopen` returns: a readable context manager."""


def answering(content: object) -> mock.Mock:
    """Return a stand-in for `urlopen` whose response body is `content`, as JSON."""
    return mock.Mock(return_value=_Response(json.dumps(content).encode()))


def model_says(text: str) -> mock.Mock:
    return answering({'choices': [{'message': {'content': text}}]})


class TestSystemPrompt:
    def test_ships_with_the_package_and_names_the_release(self):
        prompt = system_prompt('canonical/operator', '3.8.3')
        assert prompt.startswith('You are drafting release notes for canonical/operator 3.8.3.')
        assert '<repo>' not in prompt
        assert '<version>' not in prompt

    def test_carries_no_maintainer_notes(self):
        # Notes for the people editing the prompt belong in the README; the
        # model reads every character of this file. The one HTML comment in
        # it is the marker the model is asked to use.
        prompt = system_prompt('canonical/operator', '3.8.3')
        assert re.findall(r'<!--.*?-->', prompt, re.DOTALL) == ['<!-- uncertain -->']


class TestUserPrompt:
    def test_has_the_release_and_its_changelog(self):
        prompt = user_prompt(
            repo='canonical/operator',
            version='3.8.3',
            previous='3.8.2',
            branch='main',
            changelog=CHANGELOG,
        )
        assert 'Commit range: 3.8.2..main' in prompt
        assert CHANGELOG.strip() in prompt
        assert 'Compare:' not in prompt
        assert 'Exemplar' not in prompt

    def test_adds_the_compare_link_and_the_exemplars_when_given(self):
        prompt = user_prompt(
            repo='canonical/operator',
            version='3.8.3',
            previous='3.8.2',
            branch='main',
            changelog=CHANGELOG,
            exemplars='## 3.8.1\n\nA good release.\n',
            compare_url='https://example.com/compare',
        )
        assert 'Compare: https://example.com/compare' in prompt
        assert prompt.endswith('# Exemplar releases\n\n## 3.8.1\n\nA good release.\n')

    def test_blank_exemplars_are_no_exemplars(self):
        prompt = user_prompt(
            repo='r/r', version='1.0.0', previous='0.9.0', branch='main', changelog='x',
            exemplars='\n\n',
        )  # fmt: skip
        assert 'Exemplar' not in prompt


class TestTidy:
    def test_unwraps_a_fence_around_the_whole_answer(self):
        assert tidy('```markdown\nSome notes.\n```\n') == 'Some notes.'
        assert tidy('```\nSome notes.\n```') == 'Some notes.'

    def test_leaves_a_fence_inside_the_notes(self):
        notes = 'Use it like this:\n\n```python\nops.main(Charm)\n```\n\nAnd that is all.'
        assert tidy(notes) == notes

    def test_strips_the_markers(self):
        # A marker in the model's answer would truncate the notes when the
        # release body is lifted back out of the pull request description.
        assert tidy('<!-- release-notes:start -->\nNotes.\n<!-- release-notes:end -->') == (
            'Notes.'
        )


class TestPlaceholder:
    def test_starts_the_way_the_release_body_recognises(self):
        # The changelog package's `release-body` matches this opening.
        assert placeholder('3.8.3', 'no key').startswith(
            '_No release notes were drafted for 3.8.3: no key._\n'
        )

    def test_is_not_hard_wrapped(self):
        # It is published in a pull request description, where GitHub turns a
        # newline into a line break.
        paragraphs = placeholder('3.8.3', 'no key').strip().split('\n\n')
        assert all('\n' not in paragraph for paragraph in paragraphs)


class TestErrorDetail:
    def http_error(self, body: bytes) -> urllib.error.HTTPError:
        return urllib.error.HTTPError(
            'https://example.com', 400, 'Bad Request', {}, io.BytesIO(body)
        )  # type: ignore[arg-type]

    def test_reads_openrouters_message(self):
        body = json.dumps({'error': {'message': 'No such model'}}).encode()
        assert error_detail(self.http_error(body)) == 'No such model'

    def test_falls_back_to_the_raw_body(self):
        assert error_detail(self.http_error(b'<html>proxy says no</html>')) == (
            '<html>proxy says no</html>'
        )

    def test_says_when_there_is_no_body(self):
        assert error_detail(self.http_error(b'')) == 'empty response body'


class TestConsoleScript:
    @pytest.fixture
    def files(self, tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
        changelog = tmp_path / 'changes-entry.md'
        changelog.write_text(CHANGELOG)
        exemplars = tmp_path / 'exemplars.md'
        exemplars.write_text('## 3.8.1\n\nA good release.\n')
        return {'changelog': changelog, 'exemplars': exemplars, 'output': tmp_path / 'notes.md'}

    def run(self, files: dict[str, pathlib.Path]) -> int:
        return _cli.main([
            '--repo',
            'canonical/operator',
            '--version',
            '3.8.3',
            '--previous',
            '3.8.2',
            '--branch',
            'main',
            '--changelog',
            str(files['changelog']),
            '--exemplars',
            str(files['exemplars']),
            '--compare-url',
            'https://example.com/compare',
            '--output',
            str(files['output']),
        ])

    def test_no_key_writes_the_placeholder_and_succeeds(self, files, capsys):
        assert self.run(files) == 0
        assert (
            files['output']
            .read_text()
            .startswith(
                '_No release notes were drafted for 3.8.3: no OPENROUTER_API_KEY is configured._'
            )
        )
        assert 'placeholder' in capsys.readouterr().err

    def test_no_model_writes_the_placeholder_and_succeeds(self, files, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        assert self.run(files) == 0
        assert 'no OPENROUTER_MODEL variable is set' in files['output'].read_text()

    def test_writes_the_tidied_draft(self, files, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        monkeypatch.setenv('OPENROUTER_MODEL', 'some/model')
        urlopen = model_says('```markdown\nA routine release.\n```')
        with mock.patch.object(urllib.request, 'urlopen', urlopen):
            assert self.run(files) == 0
        assert files['output'].read_text() == 'A routine release.\n'

        request = urlopen.call_args.args[0]
        assert request.get_header('Authorization') == 'Bearer sk-test'
        payload = json.loads(request.data)
        assert payload['model'] == 'some/model'
        system, user = payload['messages']
        assert system['content'].startswith(
            'You are drafting release notes for canonical/operator'
        )
        assert 'Compare: https://example.com/compare' in user['content']
        assert '## 3.8.1' in user['content']

    def test_a_failed_call_writes_the_placeholder_and_succeeds(self, files, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        monkeypatch.setenv('OPENROUTER_MODEL', 'some/model')
        error = urllib.error.HTTPError(
            'https://example.com',
            400,
            'Bad Request',
            {},  # type: ignore[arg-type]
            io.BytesIO(json.dumps({'error': {'message': 'No such model'}}).encode()),
        )
        with mock.patch.object(urllib.request, 'urlopen', mock.Mock(side_effect=error)):
            assert self.run(files) == 0
        assert 'No such model' in files['output'].read_text()

    def test_an_unreachable_openrouter_writes_the_placeholder(self, files, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        monkeypatch.setenv('OPENROUTER_MODEL', 'some/model')
        error = urllib.error.URLError('no route to host')
        with mock.patch.object(urllib.request, 'urlopen', mock.Mock(side_effect=error)):
            assert self.run(files) == 0
        assert 'could not reach OpenRouter' in files['output'].read_text()

    def test_an_unexpected_response_writes_the_placeholder(self, files, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        monkeypatch.setenv('OPENROUTER_MODEL', 'some/model')
        with mock.patch.object(urllib.request, 'urlopen', answering({'choices': []})):
            assert self.run(files) == 0
        assert 'unexpected response shape' in files['output'].read_text()

    def test_an_empty_answer_writes_the_placeholder(self, files, monkeypatch):
        monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-test')
        monkeypatch.setenv('OPENROUTER_MODEL', 'some/model')
        with mock.patch.object(urllib.request, 'urlopen', model_says('   ')):
            assert self.run(files) == 0
        assert 'the model answered with nothing' in files['output'].read_text()
