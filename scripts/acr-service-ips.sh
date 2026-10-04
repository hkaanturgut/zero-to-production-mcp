#!/bin/sh
# IPv4 ranges of the AzureContainerRegistry service tag in a region, comma-separated.
# The registry firewall allows them so ACR remote builds (azd deploy) keep working.
#   usage: acr-service-ips.sh [region]   (default: $AZURE_LOCATION or canadacentral)
set -e
region="${1:-${AZURE_LOCATION:-canadacentral}}"
tag="AzureContainerRegistry.$(az account list-locations --query "[?name=='$region'].displayName | [0]" -o tsv | tr -d ' ')"
az network list-service-tags --location "$region" \
  --query "values[?name=='$tag'].properties.addressPrefixes | [0]" -o tsv \
  | grep -v ':' | paste -sd, -
