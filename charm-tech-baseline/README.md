# charm-tech-baseline

Audits a repository against the Canonical Charm Tech baseline that the 26.10
cycle distilled from SSDLC (SEC0023-SEC0061), the Astral OSS-security review,
and per-tool measurement work. It emits a JSON report of findings and can
apply the mechanical fixes.

This is the deterministic half of a pair. The other half is the
`charm-tech-baseline` skill in
[`canonical/charm-tech`](https://github.com/canonical/charm-tech), which is
what an agent reads: when a check applies, what a finding means, which
decisions are already settled, and which tools were measured and skipped.
The split is deliberate. Prose that an agent reads belongs next to the other
skills; code that has to be run, tested and linted belongs here, where it
gets a lockfile and CI.

## Use

```shell
uvx --from "git+https://github.com/canonical/charm-tech-code@<40-char-sha>#subdirectory=charm-tech-baseline" \
  charm-tech-baseline check --tier=product
```

- `check` runs every check that applies to the tier and prints one JSON
  report. `--only=security-md,dependabot` narrows it; `--format=markdown`
  is for reading rather than for parsing.
- `detect-tier` prints `product`, `canonical`, `personal` or `unknown`,
  which is what `check` does for itself when `--tier` is not given.
- `fix <name>` applies one mechanical fix, for example
  `fix add-code-of-conduct`.
- `list` prints the check and fix names.

Every check reports one of `pass`, `fail`, `na` or `unknown`. `unknown` means
the answer lives somewhere this cannot see - a Drive sheet, a spreadsheet -
and needs a person to look; it is not a quieter `pass`.

## Layout

| path | what it is |
|---|---|
| `checks/` | one module per control, each with a `CHECK_ID` and a `main()` |
| `fixes/` | one module per mechanical remediation |
| `assets/` | templates the fixes copy, and the per-repo AGENTS.md question batteries |
| `common.py` | exit codes, tier matching, result emission |
| `tier.py` | tier detection from the origin remote, resolving forks to upstream |

Checks are imported and called in process by the runner rather than being
shelled out to, so the report is assembled without a round trip through JSON.
A check invoked on its own still prints its own single-line result, which is
how the tests drive them.

Adding a check means adding a module to `checks/` with a `CHECK_ID` and a
`main()` that calls `emit_check` exactly once. The runner finds it, and no
registry needs updating.

## Developing

```shell
uv sync --group unit
uv run pytest
```
