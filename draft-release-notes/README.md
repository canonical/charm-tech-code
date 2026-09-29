# draft-release-notes

Drafts a release's notes with a model, for a human to edit before the release is published.

The changelog is the reference, and the `changelog` package generates it deterministically. Release notes are the explanation: what someone using the project should know about this release, and why it matters to them. A model writes the first draft, a human edits it in the release pull request's description, and that edited text becomes the body of the GitHub release.

Without an API key, or a model to use, or if the call fails, it writes a short placeholder asking the reviewer to write the notes themselves, and still exits successfully. A release is never blocked on drafting prose that a human is going to rewrite anyway.

## Running it

```shell
uvx --from "git+https://github.com/canonical/charm-tech-code@<40-char-sha>#subdirectory=draft-release-notes" \
  draft-release-notes \
    --repo "$GITHUB_REPOSITORY" --version "$VERSION" --previous "$PREVIOUS" --branch "$BRANCH" \
    --changelog changes-entry.md --exemplars exemplars.md \
    --compare-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/compare/$PREVIOUS...$VERSION" \
    --output release-notes.md
```

`--changelog` is this release's entry, as `changelog changes-entry` prints it. `--exemplars` is optional: the bodies of a few past releases whose notes are worth writing like, which is the only thing a repository chooses for itself. The key and the model come from the environment, as `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`.

`canonical/operator`'s `.github/workflows/propose-release.yaml` is the calling side, including how it fetches the exemplars and wraps the notes in the `release-notes` markers that the `changelog` package's `release-body` reads them back out of.

## The prompt

`src/charm_tech_code/draft_release_notes/prompt.md` is the Charm Tech release-notes prompt. Release notes across our repositories should read the same way, so every repository that uses this gets the same prompt: edit it when the drafts come out wrong, but not to suit one repository. `<repo>` and `<version>` are filled in when it is sent.

The model reads every character of the file, so notes for the people editing it belong here rather than in it.

## Developing

```shell
uv sync --group unit
uv run pytest
```
