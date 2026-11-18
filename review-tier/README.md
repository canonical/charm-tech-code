# review-tier

Decides how many approvals a pull request needs, and fails until it has them.

The repository's ruleset requires one approval and this check as a required status. A PR that is a small change passes with one approval; anything else needs two. The configuration is read from the PR's base branch, never its head, so a PR can't change the rules it's judged by.

## The tiers

A PR needs one approval if it matches one of these, and two otherwise:

* **Team PRs on low-risk paths.** The author is on the team list in the configuration, every changed file (and, for a rename, where it came from) matches an `allow` glob and no `except` glob, and fewer than `line-limit` lines changed.
* **Dependabot bumps.** Dependabot opened the PR, every commit is a signed `dependabot[bot]` commit, and no update is a semver major. The kind comes from the `update-type` lines Dependabot writes into each commit message. When an update has none (security updates sometimes don't), the check compares the major versions in the title, and treats any change on a `0.x` version as major.
* **Automated release PRs.** The release workflow opened the PR from a release branch, and only the release files changed. In the `line-checked` files the only changed lines are versions and pins between our own packages, and comparing the base and head lockfile as TOML, the only differences are our own packages' versions and their pins on each other. Human commits are fine: the check is on content, not authorship.
* **Bot updates.** The bot opened the PR from one of its fixed branches, only that branch's files changed, and every changed line matches the branch's `lines` pattern if it has one.

Anyone can add the `full-review` label to ask for two approvals. The label is sticky: once it has been added, the PR needs two approvals even if it's removed. Nothing lowers a tier.

An approval counts if it's from someone other than the author and not a bot, and it's still that reviewer's latest decision: requesting changes, or having the approval dismissed, takes it away. Each reviewer counts once.

The check's job summary, and its failure message, say which rule decided the tier and why.

## Running it

```yaml
run: uvx --from "git+https://github.com/canonical/charm-tech-code@<40-char-sha>#subdirectory=review-tier" review-tier "$PR_NUMBER"
```

It reads `GITHUB_REPOSITORY` and `GITHUB_TOKEN` from the environment, and needs only `contents: read` and `pull-requests: read`. It has no secrets and needs no org-read token, so it runs the same on a PR from a fork. See `canonical/operator`'s `.github/workflows/review-tier.yaml` for the calling side and `.github/review-tier.toml` for a configuration.

## Developing

```shell
uv sync --group unit
uv run pytest
```
