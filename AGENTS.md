# Working in cartograph-oidc

Read this before touching anything.

## What this is

A distribution of Cartograph for an organisation that signs people in
through its own directory. It adds no code to Cartograph. It configures
released pieces: Dex as the OIDC provider in front of the directory,
oauth2-proxy in front of Cartograph, and Cartograph's access by role
and team (cartograph-engine `docs/adr/0011`). It is the test of
whether Cartograph can be extended and integrated without a fork.

## Commands

Every command is a `just` recipe in the flake's toolchain; Docker comes
from the host.

| Do | Run |
|---|---|
| Start it locally | `just up` |
| The end-to-end test against it | `just e2e` |
| Validate the chart, check the tree | `just ci` |
| Stop it | `just down` |

## Rules that are not negotiable

- **No Cartograph code here.** A behaviour Cartograph lacks is a change
  to cartograph-engine or cartograph-ui first, released, then pinned
  here.
- **Pinned versions.** Every image and chart names its version. A bump
  is its own commit, with `just e2e` passing against it.
- **Only the proxy reaches Cartograph.** Cartograph trusts the identity
  headers it is sent. Nothing here may publish its port or route to it
  except through oauth2-proxy.
- **Fictional people only.** The directory in `config/glauth.cfg` is
  Cartograph's running example under example.org. No real organisation,
  person or group name anywhere.
- **Commits** in Google's Angular format (`CONTRIBUTING.md`), checked by
  `just commit-check`. Upstream is the product: no notes, logs or
  screenshots.
- **Never run `git` or `jj` write commands** unless the person asks for
  that in so many words.
