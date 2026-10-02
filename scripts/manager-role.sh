#!/bin/sh
# Give or take the sales-manager app role for the signed-in user in the current azd env.
#   ./scripts/manager-role.sh on    the $900 discount asks for confirmation in VS Code
#   ./scripts/manager-role.sh off   the $900 discount is refused (the finale default)
# Sign out and back in to the MCP server in VS Code afterwards to get a fresh token.
set -e
CID=$(azd env get-value ENTRA_CLIENT_ID)
SP=$(az ad sp show --id "$CID" --query id -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)
ROLE=$(az ad sp show --id "$CID" --query "appRoles[?value=='dms.manager'].id | [0]" -o tsv)
case "$1" in
  on)
    az rest --method post --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP/appRoleAssignedTo" \
      --body "{\"principalId\":\"$ME\",\"resourceId\":\"$SP\",\"appRoleId\":\"$ROLE\"}" >/dev/null && echo "manager: on" ;;
  off)
    AID=$(az rest --method get --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP/appRoleAssignedTo" \
      --query "value[?principalId=='$ME' && appRoleId=='$ROLE'].id | [0]" -o tsv)
    [ -n "$AID" ] && az rest --method delete --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP/appRoleAssignedTo/$AID" >/dev/null
    echo "manager: off" ;;
  *) echo "usage: $0 on|off"; exit 1 ;;
esac
