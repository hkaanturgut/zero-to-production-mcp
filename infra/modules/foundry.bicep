// Optional: Microsoft Foundry account + project + model for the agent demo.
// The agent and its MCP tool connection are configured afterwards (docs/foundry-agent.md).
param environmentName string
param location string
param tags object
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
param modelCapacity int = 50

var token = toLower(uniqueString(subscription().id, environmentName, location))

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${environmentName}-${token}'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-${environmentName}-${token}'
    allowProjectManagement: true
    disableLocalAuth: true // Entra ID only, no API keys
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: 'sales-assistant'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Sales assistant (${environmentName})'
    description: 'Agent that calls the dealer MCP server'
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: modelName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
  }
}

output endpoint string = account.properties.endpoint
output projectPrincipalId string = project.identity.principalId
