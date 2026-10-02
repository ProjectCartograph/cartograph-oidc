# Security

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's
private vulnerability reporting on this repository ("Report a
vulnerability" under the Security tab), which reaches the maintainers
only. Say what you found, how to reproduce it, and what you think the
impact is. You will get an acknowledgement within five working days and
a fix or a plan within thirty.

## What counts here

This repository is configuration: how Dex, oauth2-proxy and Cartograph
are put together. Report a way, with what is shipped here, to reach
Cartograph without signing in, to sign in as someone else, to gain a
role or a team the directory and the access list do not give, or to
make a default here leak a secret.

Cartograph trusts the identity headers it receives by design, so the
compose file publishes only oauth2-proxy's port and the chart's
NetworkPolicy admits only oauth2-proxy. A deployment that exposes
Cartograph another way has removed that protection; that is not a
vulnerability here.

A problem in Cartograph itself belongs to cartograph-engine's own
security reporting; one in Dex or oauth2-proxy, to those projects.
