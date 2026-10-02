# Contributing

`AGENTS.md` is the short brief. This is the loop.

1. Install Nix with the Determinate installer, and Docker.
2. `git config core.hooksPath .githooks` once, so every commit message
   is checked as you write it.
3. Change the configuration, then `just up` and `just e2e`. A change
   that alters who may do what changes `scripts/e2e.py` with it.
4. `just ci` validates the chart and checks the tree.

A behaviour Cartograph does not have yet is not added here: propose it
to cartograph-engine or cartograph-ui, and pin the release that brings
it.

## Commit messages

Every commit follows Google's Angular commit message format
([Angular: commit message guidelines](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md)),
strictly. `just commit-check` checks the parts a script can check, in
CI on every pull request and in the commit-msg hook.

**One change per commit.** A commit does one thing, and the tree builds
and passes its tests after it. If the summary needs "and" to say what the
commit does, it is two commits. A bug found while doing something else
is its own commit, before or after, never folded in.

**The header** is `<type>(<scope>): <summary>`, 72 characters at most.

The type is one of Angular's:

- `build`: the build, the release, or an external dependency
- `ci`: the CI configuration and its scripts
- `docs`: documentation only
- `feat`: a new feature
- `fix`: a bug fix
- `perf`: a change that makes something faster
- `refactor`: a change that neither fixes a bug nor adds a feature
- `test`: a missing test added, or a test corrected

The scope names the area the change is in; a change across several
has none. In this repository:

- `chart`: chart/, the Kubernetes install
- `commits`: the commit message check
- `compose`: compose.yaml, the local install
- `contributing`: CONTRIBUTING.md, AGENTS.md
- `dex`: config/dex.yaml and the connector examples
- `directory`: config/glauth.cfg, the fictional directory
- `docs`: README.md and docs/
- `e2e`: scripts/e2e.py
- `proxy`: oauth2-proxy's settings
- `release`: versions pinned here
- `seed`: seed/, the example projects

The summary says what the commit does, in the imperative, present
tense ("drop the stale index", not "dropped" or "drops"), starting
lower-case and with no period at the end. It stands on its own:
someone skimming the history learns what changed without reading the
body.

**A blank line**, then **the body**, required for every type but
`docs`, for the reader who was not there:

- what the problem was, and why it mattered;
- why this approach, and what was considered and rejected;
- any shortcoming the change leaves, and what would remove it;
- what you ran and what it printed, where that is the evidence.

Write prose. Wrap at 72 characters. Name files, functions and
settings exactly. A link is fine, with enough said that the commit
still makes sense if the link stops working.

**The footer** says what a change breaks or deprecates, each in its own
paragraph after the body:

```
BREAKING CHANGE: <what breaks>

<what to do instead>
```

```
DEPRECATED: <what is deprecated>

<what to use instead>
```

A revert's header is `revert: ` and the reverted header, and its body
says `This reverts commit <SHA>.` and why.

**Trailers** go last, one per line: `Fixes #12` or `Refs #12` where an
issue exists, then `Signed-off-by:` (required: `git commit -s`, the
Developer Certificate of Origin), then any `Co-authored-by:`.

A good message:

```
fix(proxy): stop asking for consent at every sign-in

oauth2-proxy sent approval_prompt=force, so Dex showed its consent
screen every time anyone signed in, though Dex is set to skip it. The
people here sign in to their own organisation's tool; there is nothing
to consent to. oauth2-proxy now sends approval_prompt=auto.

just e2e: every check passed; it stopped at Dex's approval page before.

Signed-off-by: A Contributor <contributor@example.org>
```

Not: "fix: bug", "fix: build", "chore: update files", "WIP", "Phase 1",
"Address review comments", or a summary that only names the files.

## Pull requests

One change per pull request, titled as its first commit's header. The
description says what you ran (`just e2e` against which images) and
what it printed.
