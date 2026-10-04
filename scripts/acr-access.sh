#!/usr/bin/env bash
# Open or close the registry firewall for this machine. The registry denies its
# public endpoint by default; CI opens it only while it builds and pushes.
#   usage: acr-access.sh open|close <registry-name> [ip]
# The IP defaults to the one the registry itself reports in its 403: GitHub-hosted
# runners reach Azure from a different address than a "what is my IP" service shows.
set -euo pipefail
action="${1:?open|close}"; acr="${2:?registry name}"; ip="${3:-}"

seen_ip() {
  local aad body
  aad=$(az account get-access-token --query accessToken -o tsv)
  body=$(curl -s -X POST "https://$acr.azurecr.io/oauth2/exchange" \
    --data-urlencode grant_type=access_token --data-urlencode "service=$acr.azurecr.io" \
    --data-urlencode "access_token=$aad")
  echo "$body" | sed -n "s/.*client with IP \\\\u0027\([0-9.]*\)\\\\u0027.*/\1/p"
}

case "$action" in
  open)
    [ -n "$ip" ] || ip=$(seen_ip)
    [ -n "$ip" ] || ip=$(curl -fsS https://api.ipify.org)
    echo "ip=$ip" >> "${GITHUB_OUTPUT:-/dev/null}"
    az acr network-rule add -n "$acr" --ip-address "$ip" -o none
    echo "Opened $acr for $ip; waiting for the rule to apply ..."
    for i in $(seq 1 30); do   # docs: "wait a few minutes for the rule to take effect"
      az acr login -n "$acr" >/dev/null 2>&1 && { echo "Registry reachable after ~$((i * 10)) s."; exit 0; }
      sleep 10
    done
    echo "Registry still unreachable after 5 min (it now sees: $(seen_ip))"; exit 1 ;;
  close)
    [ -n "$ip" ] || { echo "close needs the IP that was opened"; exit 1; }
    az acr network-rule remove -n "$acr" --ip-address "$ip" -o none 2>/dev/null || true
    echo "Closed $acr for $ip." ;;
  *) echo "usage: $0 open|close <registry> [ip]"; exit 1 ;;
esac
