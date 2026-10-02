# Generate the MCP-server-to-DMS service key once per azd environment.
$existing = azd env get-value DMS_API_KEY 2>$null
if (-not $existing -or $LASTEXITCODE -ne 0) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  azd env set DMS_API_KEY ([System.BitConverter]::ToString($bytes) -replace '-', '').ToLower() | Out-Null
  Write-Host "Generated DMS_API_KEY for this environment."
}
