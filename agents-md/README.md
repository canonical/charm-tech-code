# agents-md

Keeps the `AGENTS.md` files across the Charm Tech estate current and load-bearing. It implements the deterministic half of the scheme for doing that: a line in `AGENTS.md` earns its place either as an *override* (the agent would confidently do the wrong thing without it) or as a *cache* (the agent would get there eventually, by reading the Makefile, tox config and CI every session). A stale line is worse than a missing one, because agents trust the file over the repo.

## Checks

| ID | What it does |
|---|---|
| `agents-md` | The file exists, and is a pointer rather than an encyclopaedia. |
| `agents-md-content` | Staleness. Extracts every command, path, symbol and tool version, runs or resolves each against the repo, and reports what no longer exists. |
| `agents-md-battery` | Runs the repo's question battery: question, checkable answer, source line. Tests whether the file changes what an agent does, rather than whether it conforms to a style. |

`agents-md fix add-agents-md` writes the template into a repo that has none.

## Use

```
uvx --from charm-tech-code-agents-md agents-md check
uvx --from charm-tech-code-agents-md agents-md check --only=agents-md-content --format=markdown
uvx --from charm-tech-code-agents-md agents-md list
```

Every check applies to every repository. A well-maintained `AGENTS.md` is worth the same in a personal fork as in a product repository, so there is no tier system here and nothing to configure per repo beyond the battery.

## Question batteries

`assets/question-batteries/*.yaml`, one per repo, keyed by upstream name. They live here rather than in the skill so that the check and the data it reads ship together. Each entry carries the question, the answer that counts as correct, and the line of `AGENTS.md` it came from, so a battery failure points at the line to fix.
