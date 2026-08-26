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


"""Validating the model's response envelope.

Hand-rolled deliberately, not the `jsonschema` package, so the script keeps
needing nothing outside the stdlib. Mirrors ENVELOPE_JSON_SCHEMA below, which
is what OpenRouter is asked to conform to; this re-checks it on the applier
side.
"""

from __future__ import annotations

from typing import Any

_ENTRY_COMMON_REQUIRED = ('action', 'body', 'dedup_reason', 'confidence')
_ENTRY_KNOWN_KEYS = {
    'action',
    'body',
    'dedup_reason',
    'confidence',
    'title',
    'labels',
    'issue_type',
    'target_issue',
}


def validate_entry(entry: Any, *, path: str, allow_also: bool = False) -> list[str]:
    """Validate one envelope entry (top-level or an `also[i]`) against the schema.

    `also` is only legal on the top-level envelope, so the caller says whether
    this is that. Without it the top-level check rejected every envelope that
    carried `also` -- which the model emits routinely, since the schema it is
    given declares the field.
    """
    errors: list[str] = []
    if not isinstance(entry, dict):
        return [f'{path}: expected an object, got {type(entry).__name__}']

    for field in _ENTRY_COMMON_REQUIRED:
        if field not in entry:
            errors.append(f"{path}: missing required field '{field}'")

    known = _ENTRY_KNOWN_KEYS | {'also'} if allow_also else _ENTRY_KNOWN_KEYS
    unknown = set(entry) - known
    if unknown:
        errors.append(f'{path}: unknown field(s) {sorted(unknown)}')

    action = entry.get('action')
    if action not in ('comment', 'new'):
        errors.append(f"{path}.action: must be 'comment' or 'new', got {action!r}")
        return errors  # can't check action-conditional fields without a valid action

    if not isinstance(entry.get('body'), str) or not entry.get('body'):
        errors.append(f'{path}.body: must be a non-empty string')
    if not isinstance(entry.get('dedup_reason'), str) or not entry.get('dedup_reason'):
        errors.append(f'{path}.dedup_reason: must be a non-empty string')
    if entry.get('confidence') not in ('high', 'medium', 'low'):
        errors.append(
            f'{path}.confidence: must be one of high/medium/low, got {entry.get("confidence")!r}'
        )

    # A field present but null counts as absent. The schema sent to OpenRouter
    # is `strict`, so models routinely return every declared property and use
    # null for the ones that do not apply to the action they chose; rejecting on
    # mere presence threw away otherwise good output.
    if action == 'new':
        for field in ('title', 'labels', 'issue_type'):
            if field not in entry:
                errors.append(f"{path}: action='new' requires '{field}'")
        if entry.get('target_issue') is not None:
            errors.append(f"{path}: action='new' must not include 'target_issue'")
        labels = entry.get('labels')
        if labels is not None and (
            not isinstance(labels, list) or not all(isinstance(x, str) for x in labels)
        ):
            errors.append(f'{path}.labels: must be an array of strings')
        if 'issue_type' in entry and not (
            entry['issue_type'] is None or isinstance(entry['issue_type'], str)
        ):
            errors.append(f'{path}.issue_type: must be a string or null')
    else:  # comment
        if 'target_issue' not in entry:
            errors.append(f"{path}: action='comment' requires 'target_issue'")
        elif not isinstance(entry['target_issue'], int) or entry['target_issue'] < 1:
            errors.append(f'{path}.target_issue: must be a positive integer')
        for field in ('title', 'labels', 'issue_type'):
            if entry.get(field) is not None:
                errors.append(f"{path}: action='comment' must not include '{field}'")

    return errors


# Fields that only mean something for one of the two actions. The model is
# given a `strict` schema, so it tends to return every declared property and
# fill in the ones that do not apply to the action it chose. Those are dropped
# rather than treated as an error: we would not act on them either way, and
# rejecting the envelope threw away a usable body and fell back to the plain
# notice.
_ACTION_ONLY_FIELDS = {
    'comment': ('title', 'labels', 'issue_type'),
    'new': ('target_issue',),
}


def drop_inapplicable_fields(entry: Any) -> tuple[Any, list[str]]:
    """Strip fields that do not apply to `entry`'s action; report what went."""
    if not isinstance(entry, dict):
        return entry, []
    fields = _ACTION_ONLY_FIELDS.get(entry.get('action'))
    if not fields:
        return entry, []
    dropped = [f for f in fields if f in entry]
    if not dropped:
        return entry, []
    return {k: v for k, v in entry.items() if k not in dropped}, dropped


def normalise_envelope(envelope: Any) -> tuple[Any, list[str]]:
    """Drop inapplicable fields from the envelope and each `also` entry."""
    if not isinstance(envelope, dict):
        return envelope, []
    cleaned, dropped = drop_inapplicable_fields(envelope)
    notes = [f'envelope: {f}' for f in dropped]
    also = cleaned.get('also')
    if isinstance(also, list):
        entries: list[Any] = []
        for i, entry in enumerate(also):
            entry, entry_dropped = drop_inapplicable_fields(entry)
            notes += [f'envelope.also[{i}]: {f}' for f in entry_dropped]
            entries.append(entry)
        cleaned = {**cleaned, 'also': entries}
    return cleaned, notes


def validate_envelope(envelope: Any) -> list[str]:
    """Validate a top-level envelope (may carry `also`).

    Returns a list of human-readable errors; empty list means valid.
    """
    if not isinstance(envelope, dict):
        return ['envelope: expected a JSON object']

    errors = validate_entry(envelope, path='envelope', allow_also=True)

    also = envelope.get('also')
    if also is not None:
        if not isinstance(also, list) or len(also) > 2:
            errors.append('envelope.also: must be an array of at most two entries')
        else:
            for i, entry in enumerate(also):
                if isinstance(entry, dict) and 'also' in entry:
                    errors.append(f"envelope.also[{i}]: nested 'also' is not allowed")
                errors.extend(validate_entry(entry, path=f'envelope.also[{i}]'))

    return errors


ENVELOPE_JSON_SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'title': 'ai-failure-notifications envelope',
    'type': 'object',
    'required': ['action', 'body', 'dedup_reason', 'confidence'],
    'properties': {
        'action': {'enum': ['comment', 'new']},
        'body': {'type': 'string', 'minLength': 1},
        'dedup_reason': {'type': 'string', 'minLength': 1},
        'confidence': {'enum': ['high', 'medium', 'low']},
        'title': {'type': 'string', 'minLength': 1},
        'labels': {'type': 'array', 'items': {'type': 'string'}},
        'issue_type': {'type': ['string', 'null']},
        'target_issue': {'type': 'integer', 'minimum': 1},
        'also': {'type': 'array', 'maxItems': 2, 'items': {'$ref': '#/$defs/envelopeEntry'}},
    },
    'additionalProperties': False,
    'allOf': [{'$ref': '#/$defs/actionConditionals'}],
    '$defs': {
        'actionConditionals': {
            'allOf': [
                {
                    'if': {'properties': {'action': {'const': 'new'}}},
                    'then': {
                        'required': ['title', 'labels', 'issue_type'],
                        'not': {'required': ['target_issue']},
                        'properties': {'labels': {'type': 'array', 'items': {'type': 'string'}}},
                    },
                },
                {
                    'if': {'properties': {'action': {'const': 'comment'}}},
                    'then': {
                        'required': ['target_issue'],
                        'not': {
                            'anyOf': [
                                {'required': ['title']},
                                {'required': ['labels']},
                                {'required': ['issue_type']},
                            ]
                        },
                    },
                },
            ]
        },
        'envelopeEntry': {
            'type': 'object',
            'required': ['action', 'body', 'dedup_reason', 'confidence'],
            'properties': {
                'action': {'enum': ['comment', 'new']},
                'body': {'type': 'string', 'minLength': 1},
                'dedup_reason': {'type': 'string', 'minLength': 1},
                'confidence': {'enum': ['high', 'medium', 'low']},
                'title': {'type': 'string', 'minLength': 1},
                'labels': {'type': 'array', 'items': {'type': 'string'}},
                'issue_type': {'type': ['string', 'null']},
                'target_issue': {'type': 'integer', 'minimum': 1},
            },
            'additionalProperties': False,
            'allOf': [{'$ref': '#/$defs/actionConditionals'}],
        },
    },
}
