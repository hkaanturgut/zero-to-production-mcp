// Private network for one environment: the Container Apps environment lives in
// `aca`, private endpoints for Key Vault and the registry live in `pe`, and the
// private DNS zones make their normal hostnames resolve to private IPs inside it.
param environmentName string
param location string
param tags object

resource vnet 'Microsoft.Network/virtualNetworks@2025-05-01' = {
  name: 'vnet-${environmentName}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: ['10.40.0.0/16'] }
    subnets: [
      {
        name: 'aca' // workload-profiles environment: /27 minimum, size can't change later
        properties: {
          addressPrefix: '10.40.0.0/23'
          delegations: [{ name: 'aca', properties: { serviceName: 'Microsoft.App/environments' } }]
        }
      }
      {
        name: 'pe'
        properties: {
          addressPrefix: '10.40.2.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

var zones = ['privatelink.vaultcore.azure.net', 'privatelink.azurecr.io']

resource dnsZones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for zone in zones: {
    name: zone
    location: 'global'
    tags: tags
  }
]

resource dnsLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (zone, i) in zones: {
    parent: dnsZones[i]
    name: 'link-${environmentName}'
    location: 'global'
    properties: {
      virtualNetwork: { id: vnet.id }
      registrationEnabled: false
    }
  }
]

output acaSubnetId string = vnet.properties.subnets[0].id
output peSubnetId string = vnet.properties.subnets[1].id
output vaultDnsZoneId string = dnsZones[0].id
output registryDnsZoneId string = dnsZones[1].id
