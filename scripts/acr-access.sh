#!/usr/bin/env bash
# Open or close the registry firewall for this machine's public IP. The registry
# denies its public endpoint by default; CI opens it only while it builds and pushes.
#   usage: acr-access.sh open|close <registry-name> [ip]
set -euo pipefail
action="${1:?open|close}"; acr="${2:?registry name}"
ip="${3:-$(curl -fsS https://api.ipify.org)}"
case "$action" in
  open)
    az acr network-rule add -n "$acr" --ip-address "$ip" -o none
    echo "Opened $acr for $ip; waiting for the rule to apply ..."
    for i in $(seq 1 30); do   # docs: "wait a few minutes for the rule to take effect"
      az acr login -n "$acr" >/dev/null 2>&1 && az acr repository list -n "$acr" -o none 2>/dev/null \
        && { echo "Registry reachable after ~$((i * 10)) s."; exit 0; }
      sleep 10
    done
    echo "Registry still unreachable after 5 min"; exit 1 ;;
  close)
    az acr network-rule remove -n "$acr" --ip-address "$ip" -o none 2>/dev/null || true
    echo "Closed $acr for $ip." ;;
  *) echo "usage: $0 open|close <registry> [ip]"; exit 1 ;;
esac
