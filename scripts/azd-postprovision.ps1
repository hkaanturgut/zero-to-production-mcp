$acr = ($env:AZURE_CONTAINER_REGISTRY_ENDPOINT -split '\.')[0]
az acr repository show --name $acr --image base/python:3.11-slim *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Mirroring python:3.11-slim into $acr ..."
  az acr import --name $acr --source docker.io/library/python:3.11-slim --image base/python:3.11-slim --force
  if ($LASTEXITCODE -ne 0) { Write-Warning "Base image import failed; builds will pull from Docker Hub." }
}
Write-Host "MCP endpoint: $env:MCP_URL"
