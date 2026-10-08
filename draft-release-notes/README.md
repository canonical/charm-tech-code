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
    --commits commits.txt --docs-url https://canonical.com/juju/docs/ops/latest \
    --output release-notes.md --title-output release-title.md
```

`--changelog` is this release's entry, as `changelog changes-entry` prints it. `--title-output` is optional: where to write a one-line summary for the release's title, the part after `X.Y.Z: `, which the model gives as a `Title:` line ahead of the notes. Like the notes, it is always written, as a placeholder when there is no model or the model did not suggest one. `--exemplars` is optional: the bodies of a few past releases whose notes are worth writing like, which is the only thing a repository chooses for itself. The key and the model come from the environment, as `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`.

`--commits` is optional, and makes a large difference to the draft: the range's commit messages, which under squash merging are the pull-request descriptions. The changelog says what changed in a line; the descriptions say what it means, often with an example the notes can use. Write the file with:

```shell
git log --reverse --no-merges --name-only --format='%x1e%s%x1f%b%x1f' "$PREVIOUS..$BRANCH" > commits.txt
```

The commits the changelog leaves out (`chore`, and a security advisory's merge) are dropped, `ci` and `test` commits keep only their subject and files, and trailers go. With `--docs-url`, a page under `--docs-dir` (`docs` unless you say otherwise) that a commit changed is passed to the model with its published address, so that a new how-to is linked rather than left as a question for the reviewer. `docs/howto/brew.md` is taken to be published at `<docs-url>/howto/brew/`, which is how the Sphinx starter pack sites serve pages.

`canonical/operator`'s `.github/workflows/propose-release.yaml` is the calling side, including how it fetches the exemplars and wraps the notes and the summary in the `release-notes` and `release-title` markers that the `changelog` package's `release-body` and `release-title` read them back out of.

## The prompt

`src/charm_tech_code/draft_release_notes/prompt.md` is the Charm Tech release-notes prompt. Release notes across our repositories should read the same way, so every repository that uses this gets the same prompt: edit it when the drafts come out wrong, but not to suit one repository. `<repo>` and `<version>` are filled in when it is sent.

The model reads every character of the file, so notes for the people editing it belong here rather than in it.

## Developing

```shell
uv sync --group unit
uv run pytest
```
