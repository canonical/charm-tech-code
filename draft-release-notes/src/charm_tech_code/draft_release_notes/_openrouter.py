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

import json
import urllib.error
import urllib.request

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'

# How long to wait for the draft. Generous: a slow draft is still cheaper
# than a human writing the notes from nothing, and the fallback is right
# there if the wait does not pay off.
TIMEOUT_SECONDS = 180


def call_openrouter(system: str, user: str, model: str, api_key: str) -> str:
    """POST the prompts to OpenRouter and return the Markdown it answers with.

    Any failure is raised as a RuntimeError, which the caller turns into the
    placeholder body.
    """
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ],
    }
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        # The URL is a literal https endpoint, not caller-controlled.
        opened = urllib.request.urlopen(  # ruff: ignore[suspicious-url-open-usage]
            request, timeout=TIMEOUT_SECONDS
        )
        with opened as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        # `str(exc)` is only ever "HTTP Error 400: Bad Request", which says
        # nothing about which of the model, the key or the request OpenRouter
        # objected to. That is in the response body.
        raise RuntimeError(f'{exc} - {error_detail(exc)}') from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f'could not reach OpenRouter: {exc}') from exc
    try:
        return body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f'unexpected response shape: {json.dumps(body)[:500]}') from exc


def error_detail(exc: urllib.error.HTTPError) -> str:
    """Return OpenRouter's own explanation of a non-2xx, as far as it can be read.

    Nothing here is allowed to raise: an unreadable explanation must not
    replace the status code that came with it.
    """
    try:
        raw = exc.read().decode(errors='replace').strip()
    except Exception:  # Any read failure means no detail, not a crash.
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
