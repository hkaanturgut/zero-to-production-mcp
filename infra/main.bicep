// azd entry point. One command builds the whole rehearsal environment:
//   azd up            provision + deploy
//   azd deploy mcp    ship new server code only (what happens on stage)
//   azd down --purge  delete everything, including the soft-deleted Key Vault
targetScope = 'subscription'

@minLength(1)
@maxLength(20)
@description('azd environment name, e.g. mcpdev. Used in every resource name.')
param environmentName string

@description('Azure region.')
param location string = 'canadacentral'

@description('Object ID of whoever runs azd (set by azd). Gets Key Vault access for troubleshooting.')
param principalId string = ''

@description('Give the deploying user the sales-manager app role (shows the confirmation flow in VS Code).')
param assignManagerRoleToDeployer bool = false

@secure()
@description('Service credential between MCP server and DMS. Generated once by the preprovision hook (scripts/azd-preprovision.sh) and kept in the azd environment.')
param dmsApiKey string = ''

@description('Entry point of the MCP container: live-server (the file built on stage) or server (the full reference build).')
@allowed(['live-server', 'server'])
param mcpCommand string = 'live-server'

@description('Comma-separated Foundry agent identity object IDs allowed to call the server (read + write roles only).')
param agentPrincipalIds string = ''

@description('Also deploy a Foundry account, project and model for the agent demo.')
param deployFoundry bool = false

@description('True after the first azd deploy (set by azd), so re-provisioning keeps the deployed image.')
param mcpExists bool = false
param dmsExists bool = false

var tags = { 'azd-env-name': environmentName, workload: 'dealer-mcp' }

resource rg 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module entra 'modules/entra.bicep' = {
  name: 'entra'
  scope: rg
  params: {
    environmentName: environmentName
    managerPrincipalId: assignManagerRoleToDeployer ? principalId : ''
    agentPrincipalIds: empty(agentPrincipalIds) ? [] : split(agentPrincipalIds, ',')
  }
}

module platform 'modules/platform.bicep' = {
  name: 'platform'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    principalId: principalId
    dmsApiKey: dmsApiKey
    mcpCommand: mcpCommand
    mcpExists: mcpExists
    dmsExists: dmsExists
    entraClientId: entra.outputs.clientId
    entraApiUri: entra.outputs.apiUri
  }
}

module foundry 'modules/foundry.bicep' = if (deployFoundry) {
  name: 'foundry'
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    tags: tags
  }
}

// azd reads these into the environment (.azure/<env>/.env)
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = platform.outputs.registryLoginServer
output AZURE_TENANT_ID string = tenant().tenantId
output MCP_URL string = '${platform.outputs.mcpBaseUrl}/mcp'
output ENTRA_CLIENT_ID string = entra.outputs.clientId
output ENTRA_API_URI string = entra.outputs.apiUri
output ENTRA_SCOPES string = '${entra.outputs.apiUri}/dms.read ${entra.outputs.apiUri}/dms.write'
output FOUNDRY_ENDPOINT string = deployFoundry ? foundry!.outputs.endpoint : ''
output FOUNDRY_PROJECT_PRINCIPAL_ID string = deployFoundry ? foundry!.outputs.projectPrincipalId : ''
