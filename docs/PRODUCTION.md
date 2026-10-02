# Running cartograph-oidc in production

This guide installs Cartograph on Kubernetes behind single sign-on with
Microsoft Entra ID. Another directory changes one step, the connector in
Dex; everything else stays as written.

What you will have: two or more Cartograph replicas on Postgres, Dex in
front of Entra ID, oauth2-proxy in front of Cartograph, one hostname for
people (`cartograph.example.org`) and one for sign-in (`sso.example.org`).
Replace both throughout.

## Before you start

- A Kubernetes cluster with an ingress controller (the values assume
  ingress-nginx) and a way to issue TLS certificates.
- A Postgres database for Cartograph, reachable from the cluster.
  Cartograph's own chart documents pooling and connection budgets
  (cartograph-engine `docs/DEPLOYMENT.md`).
- Rights to register an application in your Entra ID tenant and to grant
  it admin consent.

## 1. Register Dex in Entra ID

In the Entra admin centre, under App registrations, register a new
application:

- Supported account types: this organisation only.
- Redirect URI (Web): `https://sso.example.org/dex/callback`.

Then:

- Under Certificates and secrets, create a client secret. Keep its
  value for step 3.
- Under API permissions, add the Microsoft Graph delegated permission
  `Directory.Read.All`, and grant admin consent. Dex needs it to read
  the names of a person's groups.
- Note the application (client) ID and the directory (tenant) ID.

`examples/entra-id/README.md` has the same steps with what Dex does at
each one.

## 2. Decide the mapping

`chart/values.yaml` under `cartograph.authz.access.mapping` says which
Entra ID groups grant which role and which groups are teams. Use the
groups' display names. A group may grant a role and be a team at once.

| Role | Give it to |
|---|---|
| reader | everyone who should see Cartograph, usually an all-staff group |
| contributor | the groups whose people define projects and keep registers |
| strategyEditor | the group that owns the strategy |
| administrator | a small group that manages access |

List the same groups under `dex.config.connectors[0].config.groups`.
With `useGroupsAsWhitelist`, Dex then passes only those groups, which
keeps the session cookie small for people in hundreds of groups, and
refuses sign-in to anyone in none of them.

Teams form a tree through `parent`. A contributor may change the work of
their teams and of every team beneath them, so put a division above its
units when its people should reach their units' work.

## 3. Create the Secrets

```
kubectl create namespace cartograph

kubectl -n cartograph create secret generic cartograph-database \
  --from-literal=url='postgres://cartograph:...@db.example.org:5432/cartograph?sslmode=require'

CLIENT_SECRET=$(openssl rand -hex 32)

kubectl -n cartograph create secret generic cartograph-dex-secrets \
  --from-literal=DEX_CLIENT_SECRET="$CLIENT_SECRET" \
  --from-literal=ENTRA_CLIENT_SECRET='the secret from step 1'

kubectl -n cartograph create secret generic cartograph-oauth2-proxy-secrets \
  --from-literal=client-id=cartograph \
  --from-literal=client-secret="$CLIENT_SECRET" \
  --from-literal=cookie-secret="$(openssl rand -base64 32 | tr -- '+/' '-_')"

kubectl -n cartograph create secret generic cartograph-agent-key \
  --from-literal=agent-key="$(openssl rand -base64 48)"
```

`DEX_CLIENT_SECRET` and `client-secret` are the same value: it is how
Dex knows oauth2-proxy. `agent-key` signs agents' tokens; changing it
signs every agent out. If your store goes through PgBouncer in
transaction mode, add `fanoutUrl` with a direct Postgres URL to
`cartograph-database` (cartograph-engine `docs/DEPLOYMENT.md`).

## 4. Set your values

Copy `chart/values.yaml` and change:

- every `example.org` host, `cartograph.agents.issuer` included;
- in the Entra ID connector, `clientID` and `tenant` from step 1;
- the groups, in the connector and in the mapping, from step 2;
- the ingress class and TLS secret names to your cluster's.

## 5. Install

```
helm repo add dex https://charts.dexidp.io
helm repo add oauth2-proxy https://oauth2-proxy.github.io/manifests
helm dependency build chart
helm install cartograph chart -n cartograph -f my-values.yaml --wait
```

After install, a Job runs `cartograph access apply`, creating the mapped
teams once. It runs again on every upgrade and creates only teams that
do not exist yet.

## 6. Check it before people arrive

- Sign in as a member of the administrator group. The rail shows
  Administration, and the Access page lists you.
- Sign in as someone in no mapped group. Dex refuses them, or, if they
  are in a whitelisted group that grants no role, Cartograph says they
  are not on the access list.
- From inside the cluster, but outside oauth2-proxy, try to reach
  Cartograph's Service directly. The NetworkPolicy must refuse it. If
  your cluster's network plugin does not enforce NetworkPolicy, enforce
  the same rule another way: anything that can reach Cartograph directly
  can claim to be anyone.

`scripts/kind-e2e` runs the same chart on a throwaway cluster against
the fictional directory, with every check above, if you want to see it
work end to end first.

## Running it

- **People leave.** Remove them from the directory group; they lose what
  it gave at their next sign-in, and oauth2-proxy refuses them once their
  session ends. Remove them on the Access page to end it at once.
- **Someone needs access the directory does not give.** Add them on the
  Access page by address, with roles and teams. The directory's part and
  yours are kept apart, and a sign-in never undoes yours.
- **The mapping changes.** Change the values and upgrade. The replicas
  restart with the new mapping, and the Job creates any new team.
- **Scaling.** Cartograph's replicas are stateless; scale them with the
  chart's autoscaling settings. Dex keeps its state in Kubernetes and
  runs as several replicas; oauth2-proxy keeps sessions in cookies, so
  its replicas need nothing shared.
