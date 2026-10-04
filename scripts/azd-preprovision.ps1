# Generate the MCP-server-to-DMS service key once per azd environment.
$existing = azd env get-value DMS_API_KEY 2>$null
if (-not $existing -or $LASTEXITCODE -ne 0) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  azd env set DMS_API_KEY ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLower() | Out-Null
  Write-Host "Generated DMS_API_KEY for this environment."
}

# Registry firewall: allow the region's ACR build service so remote builds work.
$region = if ($env:AZURE_LOCATION) { $env:AZURE_LOCATION } else { 'canadacentral' }
$display = (az account list-locations --query "[?name=='$region'].displayName | [0]" -o tsv) -replace ' ', ''
$ips = az network list-service-tags --location $region --query "values[?name=='AzureContainerRegistry.$display'].properties.addressPrefixes | [0]" -o tsv |
  Where-Object { $_ -notmatch ':' }
azd env set ACR_ALLOWED_IPS ($ips -join ',') | Out-Null
