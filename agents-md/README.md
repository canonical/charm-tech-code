# agents-md

Keeps the `AGENTS.md` files across the Charm Tech estate current and load-bearing. This is the deterministic half of the validation: a line in `AGENTS.md` earns its place either as an *override* (the agent would confidently do the wrong thing without it) or as a *cache* (the agent would get there eventually, by reading the Makefile, tox config and CI every session). A stale line is worse than a missing one, because agents trust the file over the repo.

## Checks

| ID | What it does |
|---|---|
| `agents-md` | The file exists, and is a pointer rather than an encyclopaedia. |
| `agents-md-content` | Staleness. Extracts every command, path, symbol and tool version, resolves each against the repo, and reports what no longer exists. With `--run` it also runs the safe commands. |
| `agents-md-battery` | Runs the repo's question battery: question, checkable answer, source line. Tests whether the file changes what an agent does, rather than whether it conforms to a style. |

`agents-md fix add-agents-md` writes the template into a repo that has none.

## Use

```
uvx --from charm-tech-code-agents-md agents-md check
uvx --from charm-tech-code-agents-md agents-md check --only=agents-md-content --format=markdown
uvx --from charm-tech-code-agents-md agents-md list
```

`check` runs nothing from `AGENTS.md` unless you pass `--run`. With it, `agents-md-content` runs each command that starts with an allowlisted tool and subcommand (`make lint`, `uv run pytest`, `go test` and so on), needs no shell, and changes nothing, and reports any that fail. That can take minutes, so leave it out of a per-change check.

`check` exits 0 whenever every check ran, whatever the findings, because the findings are in the report. It exits 1 when a check raised or produced no result, which the report lists under `notes`, and 2 on a usage error such as an unknown flag.

## Question batteries

`assets/question-batteries/*.yaml`, one per repo, keyed by upstream name. They live here rather than in the skill so that the check and the data it reads ship together. Each entry carries the question, the answer that counts as correct, and the line of `AGENTS.md` it came from, so a battery failure points at the line to fix.
