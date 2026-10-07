# ai-failure-notifier

Enriches the placeholder issue that a scheduled workflow's failure notifier opens.

When a scheduled workflow fails, the notifier in the repository opens an issue with a generic title and a link to the failing job. This tool picks that placeholder up, reads the failing run's job logs, reduces them to a deterministic failure signature, searches for issues that look like the same failure, and then either comments on the existing one or rewrites the placeholder with a real title, body and labels.

Without an API key it falls back to a plain notification. That is deliberate: the notifier has to work when everything else is broken, so nothing here is allowed to be a hard dependency of it.

## Running it

```shell
uvx --from "git+https://github.com/canonical/charm-tech-code@<40-char-sha>#subdirectory=ai-failure-notifier" ai-failure-notifier
```

It reads its inputs from the environment: `GH_TOKEN`, `REPO`, `RUN_ID`, `WORKFLOW_NAME`, `RUN_URL`, and optionally `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`. See `canonical/operator`'s `.github/workflows/ai-failure-enrich.yaml` for the calling side, including the environment mechanics the key depends on.

`OPENROUTER_MODEL` defaults to `deepseek/deepseek-chat`. The request lists it first and `deepseek/deepseek-v3.2` after it, so OpenRouter moves to the second model when the first one errors or is rate-limited, and an enriched issue or comment records the model that answered in a hidden `<!-- ai-failure-notifications:model ... -->` comment. A rate limit, a 5xx, a timeout or a dropped connection is retried twice, waiting at most a minute in total, before the tool falls back to the plain notification.

## Developing

```shell
uv sync --group unit
uv run pytest
```
