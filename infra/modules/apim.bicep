// API Management in front of the MCP server: the single public entry point,
// and the place the per-caller rate limit is enforced for every replica at once.
// Developer tier: a static public IP (the MCP app accepts traffic only from it),
// no SLA, 30 to 40 minutes to create. Use Premium (v2) for production SLAs.
param environmentName string
param location string
param tags object
param publisherEmail string

var token = toLower(uniqueString(subscription().id, environmentName, location))

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: 'apim-${environmentName}-${take(token, 8)}'
  location: location
  tags: tags
  sku: { name: 'Developer', capacity: 1 }
  properties: {
    publisherEmail: publisherEmail
    publisherName: 'Dealer MCP (${environmentName})'
  }
}

output name string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
output publicIp string = apim.properties.publicIPAddresses[0]
