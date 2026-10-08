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


"""The OpenRouter call."""

from __future__ import annotations

import email.utils
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from ._constants import FALLBACK_MODELS, MAX_RETRY_WAIT, MAX_TOTAL_RETRY_WAIT, RETRY_DELAYS
from ._envelope import ENVELOPE_JSON_SCHEMA


def model_list(model: str) -> list[str]:
    """The `models` routing list: `model` first, then the fallbacks, without repeats."""
    models = [model]
    models.extend(fallback for fallback in FALLBACK_MODELS if fallback != model)
    return models


def call_openrouter(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    *,
    sleep: Callable[[float], object] | None = None,
) -> tuple[dict[str, Any], str]:
    """POST the prompt to OpenRouter with the envelope schema.

    Returns the parsed JSON and the model that answered, which is not always
    `model`: the request names `model` and then FALLBACK_MODELS, and
    OpenRouter moves down that list when a model errors, a provider rate limit
    included.

    Uses urllib rather than requests so the script has no third-party
    dependencies at all. A rate limit, a 5xx, a timeout or a connection
    failure is retried a couple of times (see `_retry_wait`); anything else,
    or the last of those, is raised as an error carrying OpenRouter's own
    explanation, which main() treats the same as any other OpenRouter
    failure: fall back to the plain body.

    `sleep` waits between attempts, `time.sleep` unless a test passes its own.
    It is looked up at call time, not bound as the default, so that a test
    suite blocking `time.sleep` catches a call that forgot to pass one.
    """
    sleep = sleep or time.sleep
    payload = {
        # `models` rather than `model`: OpenRouter's model fallback list, in
        # priority order. The `provider` preferences below apply to each
        # model in it.
        'models': model_list(model),
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'ai_failure_notification',
                'strict': True,
                'schema': ENVELOPE_JSON_SCHEMA,
            },
        },
        # Without this, OpenRouter may route to a provider that ignores
        # `response_format`, and the schema above is only a suggestion.
        'provider': {'require_parameters': True},
    }
    request = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    attempts = len(RETRY_DELAYS) + 1
    waited = 0.0
    for attempt in range(1, attempts + 1):
        try:
            # The URL is a literal https endpoint, not caller-controlled.
            with urllib.request.urlopen(request, timeout=60) as response:  # ruff: ignore[suspicious-url-open-usage]
                body = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            # `str(exc)` is only ever "HTTP Error 400: Bad Request", which says
            # nothing about which of the model, the key or the schema OpenRouter
            # objected to. The reason is in the response body, and reading it is
            # the difference between a glance and an afternoon.
            failure = f'{exc} - {_error_detail(exc)}'
            transient = exc.code == 429 or exc.code >= 500
            retry_after = _retry_after(exc)
            error: Exception = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            # A timeout or a dropped connection, before or during the read.
            # `socket.timeout` is `TimeoutError` from Python 3.10.
            failure = str(exc)
            transient = True
            retry_after = None
            error = exc
        else:
            return _parse_reply(body, model)
        wait = _retry_wait(attempt, retry_after, waited) if transient else None
        if wait is None:
            tries = f'{attempt} attempt' + ('s' if attempt > 1 else '')
            raise RuntimeError(f'{failure} (after {tries})') from error
        print(
            f'OpenRouter attempt {attempt} of {attempts} failed ({failure.splitlines()[0]}); '
            f'retrying in {wait:g}s.',
            file=sys.stderr,
            flush=True,
        )
        sleep(wait)
        waited += wait
    # Unreachable: the last attempt either returns or has no wait, and raises.
    raise AssertionError('retry loop exited without a result')


# Some providers wrap the JSON in a Markdown code fence even under the strict
# `json_schema` response format. Only a fence around the whole reply is removed:
# the envelope is still validated afterwards, like any other reply.
_FENCED = re.compile(r'\A\s*```(?:json)?[ \t]*\n(?P<inner>.*)\n[ \t]*```\s*\Z', re.DOTALL)


def _parse_reply(body: dict[str, Any], requested: str) -> tuple[dict[str, Any], str]:
    """The envelope from a chat completion, and the model OpenRouter says produced it."""
    content = body['choices'][0]['message']['content']
    answered_by = str(body.get('model') or requested)
    print(f'OpenRouter answered with model {answered_by}.', file=sys.stderr, flush=True)
    fenced = _FENCED.match(content)
    if fenced:
        print(
            'The reply was in a Markdown code fence; parsing inside it.',
            file=sys.stderr,
            flush=True,
        )
        content = fenced['inner']
    return json.loads(content), answered_by


def _retry_wait(attempt: int, retry_after: float | None, waited: float) -> float | None:
    """How long to wait before the next attempt, or None to stop retrying.

    `attempt` is the one that just failed, counting from 1. OpenRouter's own
    `Retry-After` wins over the default delay when it sends one, but no single
    wait is longer than MAX_RETRY_WAIT and the waits together are no longer
    than MAX_TOTAL_RETRY_WAIT: past that, the plain fallback body now is worth
    more than an enriched one later.
    """
    if attempt > len(RETRY_DELAYS):
        return None
    wanted = RETRY_DELAYS[attempt - 1] if retry_after is None else retry_after
    wait = min(wanted, MAX_RETRY_WAIT, MAX_TOTAL_RETRY_WAIT - waited)
    return wait if wait > 0 else None


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """The `Retry-After` header in seconds, if there is a usable one.

    It is either a number of seconds or an HTTP date. Anything else, or a time
    already past, is treated as absent.
    """
    value = exc.headers.get('Retry-After') if exc.headers else None
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        seconds = when.timestamp() - time.time()
    return seconds if seconds > 0 else None


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """OpenRouter's own explanation of a non-2xx, as far as it can be read.

    The body is JSON in the ordinary case and can be anything at all when a
    proxy answers instead, so nothing here is allowed to raise: an unreadable
    explanation must not replace the status code that came with it.
    """
    try:
        raw = exc.read().decode(errors='replace').strip()
    except Exception:
        # Any read failure means no detail, not a crash.
        return 'no response body'
    if not raw:
        return 'empty response body'
    try:
        parsed = json.loads(raw)
    except ValueError:
        return raw[:500]
    error = parsed.get('error') if isinstance(parsed, dict) else None
    if isinstance(error, dict) and error.get('message'):
        return str(error['message'])[:500]
    return raw[:500]
