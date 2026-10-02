# cartograph-oidc: every command runs inside the flake's toolchain.
set shell := ["nix", "develop", "--command", "bash", "-c"]

# Start everything on this machine (compose.yaml); open http://localhost:4180
up:
    scripts/cartograph-image
    docker compose up -d --wait

# Stop it and drop its database
down:
    docker compose down -v

# Sign each fictional person in and check what they may see and do
e2e url="http://localhost:4180":
    python3 scripts/e2e.py {{url}}

# The chart on a throwaway kind cluster, with the same checks from a pod
kind-e2e:
    scripts/kind-e2e

# What CI runs: the chart renders and validates, the tree is clean
ci: chart clean-tree

# The chart: its dependencies fetched, linted, rendered and validated
chart:
    helm repo add dex https://charts.dexidp.io --force-update >/dev/null
    helm repo add oauth2-proxy https://oauth2-proxy.github.io/manifests --force-update >/dev/null
    helm dependency build chart >/dev/null
    helm lint --strict chart
    helm template cartograph chart | kubeconform -strict -summary -ignore-missing-schemas

# Commit messages since main follow CONTRIBUTING.md
commit-check base="origin/main":
    scripts/check-commit-msg {{base}}

# Nothing but the product is tracked
clean-tree:
    scripts/check-clean-tree
