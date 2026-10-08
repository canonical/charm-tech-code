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


"""Build the prompts, and tidy what comes back."""

from __future__ import annotations

import importlib.resources
import pathlib
import re

# The release pull request's description wraps the notes and the title's
# summary in these, so that they can be lifted back out of it later (the
# `changelog` package's `release-body` and `release-title`). A model that
# emits one of them itself would cut its own text short, so they are stripped
# from whatever comes back.
MARKERS = re.compile(r'<!--\s*release-(?:notes|title):(?:start|end)\s*-->')

# The line the prompt asks the answer to start with. Bold is tolerated, since
# a model asked for Markdown sometimes adds it.
TITLE_LINE = re.compile(r'\A\**Title:\**\s*(?P<summary>.*?)\s*\Z', re.IGNORECASE)

# A model told to emit Markdown and nothing else sometimes wraps the lot in a
# fence anyway.
WRAPPING_FENCE = re.compile(r'\A```(?:markdown|md)?\n(?P<body>.*)\n```\s*\Z', re.DOTALL)

# The `git log` format `--commits` expects, with `--name-only`: a record
# separator, the subject, a unit separator, the body, and another unit
# separator, after which git lists the files the commit changed.
COMMITS_LOG_FORMAT = '%x1e%s%x1f%b%x1f'

# Commits the changelog leaves out, so the model is not shown them either: a
# `chore`, and the merge of a security advisory's private fork, whose fix has
# already been released. These mirror the `changelog` package's
# `IGNORED_TYPES` and `ADVISORY_MERGE_SUBJECT`.
SKIPPED_SUBJECT = re.compile(r'\Achore(?:\([^()]*\))?!?:|\AMerge commit from fork\Z')

# Commits whose body the model is not shown, only the subject and files: the
# prompt has it leave CI and our own tests out, so the detail is no use.
SUBJECT_ONLY = re.compile(r'\A(?:ci|test)(?:\([^()]*\))?!?:')

# Trailers that say who wrote a commit, which is not what the model is for.
TRAILER = re.compile(r'^(?:Co-authored-by|Signed-off-by):.*$\n?', re.MULTILINE | re.IGNORECASE)

# A squash commit's body ends with a line of dashes above the trailers.
DASHES = re.compile(r'^-{3,}\s*$\n?', re.MULTILINE)

# How much of each commit the model sees. A pull-request description is
# usually far shorter; this is for the ones that paste a log into it.
MAX_BODY = 4000
MAX_FILES = 20


def commit_digest(log_text: str, *, docs_url: str | None = None, docs_dir: str = 'docs') -> str:
    """Return the commit messages for the model to read, from a `--commits` log.

    `log_text` is ``git log --reverse --no-merges --name-only`` output in
    `COMMITS_LOG_FORMAT`. Each commit the changelog would list is kept, with
    its body (trailers dropped, and cut short if it is very long) and the
    files it changed. A `ci` or `test` commit keeps only its subject and
    files, since those are left out of the notes. With a `docs_url`, each
    Markdown or reStructuredText page under `docs_dir` that a commit changed
    is also given as the address it is published at, so that the model can
    link it rather than ask for the link: `docs/howto/secure-your-charm.md` under
    `https://example.com/docs` is `https://example.com/docs/howto/secure-your-charm/`.
    """
    sections: list[str] = []
    for record in log_text.split('\x1e'):
        subject, _, rest = record.partition('\x1f')
        body, _, files_text = rest.partition('\x1f')
        subject = subject.strip()
        if not subject or SKIPPED_SUBJECT.search(subject):
            continue
        if SUBJECT_ONLY.search(subject):
            body = ''
        body = DASHES.sub('', TRAILER.sub('', body)).strip()
        if len(body) > MAX_BODY:
            body = body[:MAX_BODY].rstrip() + '\n[...]'
        files = [line.strip() for line in files_text.splitlines() if line.strip()]
        lines = [f'## {subject}', '']
        if body:
            lines += [body, '']
        if files:
            shown = ', '.join(files[:MAX_FILES])
            more = f' (and {len(files) - MAX_FILES} more)' if len(files) > MAX_FILES else ''
            lines.append(f'Files: {shown}{more}')
        pages = [doc_page_url(f, docs_url, docs_dir) for f in files] if docs_url else []
        pages = [page for page in pages if page]
        if pages:
            lines.append(f'Documentation pages: {", ".join(pages)}')
        sections.append('\n'.join(lines).strip())
    return '\n\n'.join(sections)


def doc_page_url(path: str, docs_url: str, docs_dir: str = 'docs') -> str | None:
    """Return where a documentation source file is published, or None if it is not a page.

    The site is assumed to serve `<docs_dir>/<path>.md` at `<docs_url>/<path>/`,
    which is how the sites built with the Canonical Sphinx Stack do it.
    An `index` page is not given: a commit changes one to list a new page,
    and the new page is the one to link.
    """
    source = pathlib.PurePosixPath(path)
    try:
        relative = source.relative_to(docs_dir.strip('/'))
    except ValueError:
        return None
    if source.suffix not in ('.md', '.rst') or any(
        part.startswith(('.', '_')) for part in relative.parts
    ):
        return None
    page = relative.with_suffix('')
    if page.name == 'index':
        return None
    return f'{docs_url.rstrip("/")}/{page}/'


def system_prompt(repo: str, version: str) -> str:
    """Return the system prompt, with the release filled in."""
    template = importlib.resources.files(__package__).joinpath('prompt.md').read_text()
    return template.replace('<repo>', repo).replace('<version>', version)


def user_prompt(
    *,
    repo: str,
    version: str,
    previous: str,
    branch: str,
    changelog: str,
    exemplars: str = '',
    compare_url: str | None = None,
    commits: str = '',
) -> str:
    """Return the user message: everything about this particular release.

    The generated changelog, the range it covers, and, if the caller has
    them, the commit messages (as `commit_digest` gives them) and the
    exemplar releases.
    """
    parts = [
        '# This release',
        '',
        f'Repository: {repo}',
        f'Version: {version}',
        f'Previous release: {previous}',
        f'Branch: {branch}',
        f'Commit range: {previous}..{branch}',
    ]
    if compare_url:
        parts.append(f'Compare: {compare_url}')
    parts += ['', '# The generated changelog for this release', '', changelog.strip()]
    if commits.strip():
        parts += ['', '# The commit messages for this release', '', commits.strip()]
    if exemplars.strip():
        parts += ['', '# Exemplar releases', '', exemplars.strip()]
    return '\n'.join(parts) + '\n'


def tidy(notes: str) -> str:
    """Return the model's Markdown with the two things it gets wrong removed."""
    notes = notes.strip()
    fence = WRAPPING_FENCE.match(notes)
    if fence:
        notes = fence.group('body').strip()
    return MARKERS.sub('', notes).strip()


def split_title(answer: str) -> tuple[str | None, str]:
    """Return the summary from the answer's `Title:` line, and the notes after it.

    The summary is None when the answer does not start with the line, or the
    line has nothing on it; the notes are then the whole answer. The line is
    only looked for at the very start, so a "Title:" further down is left as
    part of the notes.
    """
    first, _, rest = answer.strip().partition('\n')
    match = TITLE_LINE.match(first.strip())
    if not match:
        return None, answer.strip()
    return match.group('summary').strip().strip('*').strip() or None, rest.strip()


def title_placeholder(version: str, reason: str) -> str:
    """Return the title summary to use when there is none: a note asking for one.

    The opening words are what the `changelog` package's `release-title`
    recognises as the placeholder, so keep them as they are.
    """
    return (
        f'_No title was drafted for {version}: {reason}. Replace this line with a short'
        f' summary, or leave it and the release is titled {version}._'
    )


def placeholder(version: str, reason: str) -> str:
    """Return the body to use when there is no draft: a note asking for one.

    The first line is what the `changelog` package's `release-body`
    recognises as the placeholder, so keep its opening words as they are.
    """
    return (
        f'_No release notes were drafted for {version}: {reason}._\n'
        '\n'
        'Write them here before merging. They become the body of the GitHub'
        ' release, above the changelog entry for this version.\n'
    )
