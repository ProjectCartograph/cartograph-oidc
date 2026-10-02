# Microsoft Entra ID through Dex

Dex's `microsoft` connector signs people in against an Entra ID tenant
and reads the names of their groups from Microsoft Graph. Cartograph
never sees Entra ID: it sees the groups, the address and the display
name Dex puts in its ID token, through oauth2-proxy.

## Register the application

In the Entra admin centre, App registrations, New registration:

1. Supported account types: accounts in this organisational directory
   only.
2. Redirect URI, platform Web: Dex's issuer followed by `/callback`, for
   example `https://sso.example.org/dex/callback`.
3. Certificates and secrets: a new client secret. Its value goes into
   Dex's environment as `ENTRA_CLIENT_SECRET`.
4. API permissions: Microsoft Graph, delegated, `Directory.Read.All`,
   then Grant admin consent. Dex reads group names with it.
5. Overview: copy the application (client) ID and the directory (tenant)
   ID into the connector below.

## The connector

`dex-connector.yaml` replaces the LDAP connector in `config/dex.yaml`
for a compose install, or goes under `dex.config.connectors` in the
chart's values (`chart/values.yaml` already has it). Dex takes:

- the person's address from `userPrincipalName`, which becomes their
  key on Cartograph's access list;
- their display name from `displayName`, which is what others see on a
  shared screen;
- their groups by display name, which is what `config/access.yaml` maps.

`groups` with `useGroupsAsWhitelist` passes on only the groups the
mapping uses, and lets only their members sign in.
