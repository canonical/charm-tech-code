# charm-tech-code

Shared tooling for the Charm Tech repositories (`operator`, `charmlibs`,
`jubilant`, `pebble`, `concierge`, and the rest of the estate).

Code here is consumed by workflow YAML in the repository that runs it, pinned
by commit SHA:

```yaml
run: uvx --from git+https://github.com/canonical/charm-tech-code@<40-char-sha> ai-failure-notifier
```

The point is that the code lives in one place. A tool used by eleven
repositories should be fixed once, not eleven times, and the workflow YAML
that differs per repository stays in that repository.

There is no release process and nothing is published. The SHA in the `uvx`
line is the version, which is the same trust decision every pinned
`uses: actions/checkout@<sha>` line in those repositories already makes.

## Tools

### `ai-failure-notifier`

Enriches the placeholder issue that a scheduled workflow's failure notifier
opens. It reads the failing run's job logs, builds a deterministic failure
signature, searches for issues that look like the same failure, and either
comments on one or rewrites the placeholder with a real title, body and
labels. Without an API key it falls back to a plain notification, so the
notifier's "always works" property is not affected by this being unavailable.

See `canonical/operator`'s `.github/workflows/ai-failure-enrich.yaml` for the
calling side.

## Developing

```shell
uv sync
uv run pytest
```
