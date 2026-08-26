# charm-tech-code

Shared tooling for the Charm Tech repositories (`operator`, `charmlibs`, `jubilant`, `pebble`, `concierge`, and the rest of the estate).

Each tool is its own package in its own top-level directory, with its own `pyproject.toml`, `src/`, `tests/` and lockfile - the same shape `canonical/charmlibs` uses. Adding a tool means adding a directory, not adding to an existing package, so a tool's dependencies are paid only by the workflows that run that tool.

| directory | what it does |
|---|---|
| [`ai-failure-notifier`](ai-failure-notifier) | Triages and enriches the issue opened when a scheduled workflow fails. |
| [`charm-tech-baseline`](charm-tech-baseline) | Audits a repository against the Charm Tech baseline, and applies the mechanical fixes. |

Code here is consumed by workflow YAML in the repository that runs it, pinned by commit SHA:

```yaml
run: uvx --from "git+https://github.com/canonical/charm-tech-code@<40-char-sha>#subdirectory=ai-failure-notifier" ai-failure-notifier
```

The point is that the code lives in one place. A tool used by eleven repositories should be fixed once, not eleven times, and the workflow YAML that differs per repository stays in that repository.

There is no release process and nothing is published. The SHA in the `uvx` line is the version, which is the same trust decision every pinned `uses: actions/checkout@<sha>` line in those repositories already makes.

## Configuration

Ruff's configuration lives in the root `pyproject.toml` and is copied from `canonical/operator`, so that a file can move between the two repositories without being reformatted. Packages deliberately do not carry their own `[tool.ruff]` block: ruff uses the closest configuration it finds rather than merging, so a local one would silently override the shared one.

`preview` is set in configuration rather than passed as `--preview` on the command line, which is how operator's `tox.ini` does it. That way an editor, a hook and CI agree without anyone having to remember the flag. It is load-bearing rather than cosmetic - the preview style hugs brackets inside calls, and without it a good deal of existing code reformats.

## Developing

```shell
cd <package>
uv sync --group unit
uv run pytest
```

Lint and format run from the root, across every package at once:

```shell
uv run --group lint ruff check .
uv run --group lint ruff format --check .
```
