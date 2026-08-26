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
import urllib.request
from typing import Any

from charm_tech_code.ai_failure_notifier.envelope import ENVELOPE_JSON_SCHEMA


def call_openrouter(
    system_prompt: str, user_prompt: str, model: str, api_key: str
) -> dict[str, Any]:
    """POST the prompt to OpenRouter with the envelope schema, return the parsed JSON.

    Uses urllib rather than requests so the script has no third-party
    dependencies at all. urlopen raises HTTPError (a subclass of OSError) on a
    non-2xx response, which main() treats the same as any other OpenRouter
    failure: fall back to the plain body.
    """
    payload = {
        'model': model,
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
    }
    request = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps(payload).encode(),
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    # S310: the URL is a literal https endpoint, not caller-controlled.
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        body = json.loads(response.read().decode())
    content = body['choices'][0]['message']['content']
    return json.loads(content)
