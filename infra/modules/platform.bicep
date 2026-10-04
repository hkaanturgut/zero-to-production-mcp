// Runtime platform: registry, secrets, observability, two container apps, all
// on a private network. Key Vault and the registry are reached through private
// endpoints; the MCP app accepts traffic only from API Management.
param environmentName string
param location string
param tags object
param principalId string
param principalType string
param entraClientId string
@description('Application ID URI of the server app registration: prefix of the advertised scopes.')
param entraApiUri string
@secure()
param dmsApiKey string
param mcpCommand string
param mcpExists bool
param dmsExists bool
param acaSubnetId string
param peSubnetId string
param vaultDnsZoneId string
param registryDnsZoneId string
@description('IPv4 ranges allowed on the registry public endpoint: the region\'s ACR service IPs, so remote builds (azd deploy) still run.')
param acrAllowedIps array
@description('Static public IP of API Management, the only client the MCP app accepts.')
param apimPublicIp string
@description('Public URL clients use (the API Management gateway); advertised in Protected Resource Metadata.')
param publicBaseUrl string

var token = toLower(uniqueString(subscription().id, environmentName, location))
// Placeholder until the first `azd deploy`: listens on 8080 like our image does.
var placeholderImage = 'mcr.microsoft.com/dotnet/samples:aspnetapp'
var mcpName = 'ca-mcp-${environmentName}'
var dmsName = 'ca-dms-${environmentName}'

// ------------------------------------------------------------------ observability
resource logs 'Microsoft.OperationalInsights/workspaces@2025-07-01' = {
  name: 'log-${environmentName}-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${environmentName}-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

// ------------------------------------------------------------------ identity
// One identity for both apps: pulls images, reads secrets. No passwords anywhere.
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-${environmentName}-${token}'
  location: location
  tags: tags
}

// ------------------------------------------------------------------ registry
resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: 'cr${replace(environmentName, '-', '')}${token}'
  location: location
  tags: tags
  sku: { name: 'Premium' } // private endpoints and firewall rules need Premium
  properties: {
    adminUserEnabled: false // identities only
    // Public endpoint denied except the region's ACR build service ranges (remote
    // builds) and a CI runner's IP while it pushes (scripts/acr-access.sh).
    // Container Apps pull through the private endpoint.
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices' // az acr import between registries
    networkRuleSet: {
      defaultAction: 'Deny'
      ipRules: [for ip in acrAllowedIps: { action: 'Allow', value: ip }]
    }
  }
}

resource registryEndpoint 'Microsoft.Network/privateEndpoints@2025-05-01' = {
  name: 'pe-acr-${environmentName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      { name: 'acr', properties: { privateLinkServiceId: registry.id, groupIds: ['registry'] } }
    ]
  }
}

resource registryDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-05-01' = {
  parent: registryEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [{ name: 'acr', properties: { privateDnsZoneId: registryDnsZoneId } }]
  }
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: registry
  name: guid(registry.id, identity.id, 'AcrPull')
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ------------------------------------------------------------------ secrets
resource vault 'Microsoft.KeyVault/vaults@2025-05-01' = {
  name: 'kv-${take(replace(environmentName, '-', ''), 10)}-${take(token, 8)}'
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7 // azd down --purge cleans it up between rehearsals
    // Data plane only through the private endpoint. Bicep still writes the secret:
    // deployments go through the control plane (management.azure.com).
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny', bypass: 'AzureServices' }
  }
}

resource vaultEndpoint 'Microsoft.Network/privateEndpoints@2025-05-01' = {
  name: 'pe-kv-${environmentName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      { name: 'vault', properties: { privateLinkServiceId: vault.id, groupIds: ['vault'] } }
    ]
  }
}

resource vaultDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2025-05-01' = {
  parent: vaultEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [{ name: 'vault', properties: { privateDnsZoneId: vaultDnsZoneId } }]
  }
}

resource dmsKeySecret 'Microsoft.KeyVault/vaults/secrets@2025-05-01' = {
  parent: vault
  name: 'dms-api-key'
  properties: {
    value: dmsApiKey
    contentType: 'service-credential'
  }
}

var kvSecretsUserRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, identity.id, 'KeyVaultSecretsUser')
  properties: {
    roleDefinitionId: kvSecretsUserRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsUserDeployer 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: vault
  name: guid(vault.id, principalId, 'KeyVaultSecretsUser')
  properties: {
    roleDefinitionId: kvSecretsUserRoleId
    principalId: principalId
    principalType: principalType
  }
}

// ------------------------------------------------------------------ container apps
resource env 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: 'cae-${environmentName}-${token}'
  location: location
  tags: tags
  properties: {
    // In the VNet so the apps reach Key Vault and the registry privately. External:
    // the MCP app has a public ingress, restricted to API Management's IP below.
    vnetConfiguration: { infrastructureSubnetId: acaSubnetId, internal: false }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

// Keep whatever image azd last deployed when provisioning again.
module mcpImage 'fetch-image.bicep' = {
  name: 'mcp-image'
  params: { name: mcpName, exists: mcpExists }
}
module dmsImage 'fetch-image.bicep' = {
  name: 'dms-image'
  params: { name: dmsName, exists: dmsExists }
}

var dmsKeySecretRef = [
  {
    name: 'dms-api-key'
    keyVaultUrl: dmsKeySecret.properties.secretUri
    identity: identity.id
  }
]

var probes = [
  { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 } }
  { type: 'Readiness', httpGet: { path: '/healthz', port: 8080 } }
]

// The dealer system: internal ingress only. Never reachable from the internet.
resource dms 'Microsoft.App/containerApps@2025-07-01' = {
  name: dmsName
  location: location
  tags: union(tags, { 'azd-service-name': 'dms' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8080
        transport: 'http'
      }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
      secrets: dmsKeySecretRef
    }
    template: {
      containers: [
        {
          name: 'dms'
          image: dmsExists ? dmsImage.outputs.image : placeholderImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'HOST', value: '0.0.0.0' }
            { name: 'PORT', value: '8080' }
            { name: 'APP_ENTRY', value: 'dms' } // same image, different entry point
            { name: 'DMS_API_KEY', secretRef: 'dms-api-key' }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 } // in-memory demo data: exactly one replica
    }
  }
  dependsOn: [acrPull, kvSecretsUser, registryDns, vaultDns]
}

// The MCP server: the only public entry point.
resource mcp 'Microsoft.App/containerApps@2025-07-01' = {
  name: mcpName
  location: location
  tags: union(tags, { 'azd-service-name': 'mcp' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        allowInsecure: false
        // Only API Management may call the server, so its rate limit can't be bypassed.
        ipSecurityRestrictions: [
          { name: 'apim', description: 'API Management gateway', ipAddressRange: '${apimPublicIp}/32', action: 'Allow' }
        ]
      }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
      secrets: concat(dmsKeySecretRef, [
        { name: 'appinsights-connection-string', value: appInsights.properties.ConnectionString }
      ])
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: mcpExists ? mcpImage.outputs.image : placeholderImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'HOST', value: '0.0.0.0' }
            { name: 'PORT', value: '8080' }
            { name: 'APP_ENTRY', value: mcpCommand }
            { name: 'AUTH_MODE', value: 'entra' }
            { name: 'ENTRA_TENANT_ID', value: tenant().tenantId }
            { name: 'ENTRA_CLIENT_ID', value: entraClientId }
            { name: 'ENTRA_API_URI', value: entraApiUri }
            { name: 'DMS_BASE_URL', value: 'http://${dmsName}' }
            { name: 'DMS_API_KEY', secretRef: 'dms-api-key' }
            { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
          ]
          // Health probes only once our image runs (the placeholder has no /healthz).
          probes: mcpExists ? probes : []
        }
      ]
      // Interactive MCP clients should never wait for a cold start.
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [{ name: 'http', http: { metadata: { concurrentRequests: '50' } } }]
      }
    }
  }
  dependsOn: [acrPull, kvSecretsUser, registryDns, vaultDns]
}

output registryLoginServer string = registry.properties.loginServer
output mcpAppName string = mcp.name
output mcpBackendUrl string = 'https://${mcp.properties.configuration.ingress.fqdn}'
