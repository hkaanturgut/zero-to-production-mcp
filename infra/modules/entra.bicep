// The MCP server as an OAuth protected resource in Microsoft Entra ID.
//
//  * Delegated scopes dms.read, dms.write: what a signed-in salesperson's client
//    (VS Code) requests. VS Code is pre-authorized, so no consent prompt on stage.
//  * App roles dms.read, dms.write (Application): for Foundry agent identities.
//  * App role dms.manager (User): only for sales managers. A role, not a scope,
//    so nobody can consent their way into manager rights.
//
// The server merges `scp` and `roles` into one permission set.
extension microsoftGraphV1

param environmentName string

@description('User or group object ID to receive the dms.manager role. Empty to skip.')
param managerPrincipalId string = ''

@description('Service principal object IDs of Foundry agent identities: get read + write, never manager.')
param agentPrincipalIds array = []

// VS Code's well-known client ID (Microsoft docs: "Secure MCP calls ... from Visual Studio Code").
var vsCodeClientId = 'aebc6443-996d-45c2-90f0-388ff96faa56'

// Stable IDs across re-deployments.
var scopeReadId = guid(subscription().id, environmentName, 'scope-dms.read')
var scopeWriteId = guid(subscription().id, environmentName, 'scope-dms.write')
var roleReadId = guid(subscription().id, environmentName, 'role-dms.read')
var roleWriteId = guid(subscription().id, environmentName, 'role-dms.write')
var roleManagerId = guid(subscription().id, environmentName, 'role-dms.manager')

resource app 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: 'dealer-mcp-${environmentName}'
  displayName: 'Dealer Sales MCP (${environmentName})'
  signInAudience: 'AzureADMyOrg'
  // Tenant-scoped URI form, allowed by the default app ID URI policy.
  identifierUris: ['api://${tenant().tenantId}/dealer-mcp-${environmentName}']
  api: {
    // v2 tokens: aud = this app's client ID, iss = .../v2.0 (what the server validates).
    requestedAccessTokenVersion: 2
    oauth2PermissionScopes: [
      {
        id: scopeReadId
        value: 'dms.read'
        type: 'User'
        isEnabled: true
        adminConsentDisplayName: 'Read dealer inventory'
        adminConsentDescription: 'Search cars, quote prices, view test-drive slots.'
        userConsentDisplayName: 'Read dealer inventory'
        userConsentDescription: 'Let the assistant search cars and quote prices for you.'
      }
      {
        id: scopeWriteId
        value: 'dms.write'
        type: 'User'
        isEnabled: true
        adminConsentDisplayName: 'Manage leads and small discounts'
        adminConsentDescription: 'Create leads, book test drives, apply discounts up to the dealer limit.'
        userConsentDisplayName: 'Manage your leads'
        userConsentDescription: 'Let the assistant create leads and apply small discounts for you.'
      }
    ]
    preAuthorizedApplications: [
      {
        appId: vsCodeClientId
        delegatedPermissionIds: [scopeReadId, scopeWriteId]
      }
    ]
  }
  appRoles: [
    {
      id: roleReadId
      value: 'dms.read'
      allowedMemberTypes: ['Application']
      displayName: 'Agent: read inventory'
      description: 'Lets an agent identity use read tools.'
      isEnabled: true
    }
    {
      id: roleWriteId
      value: 'dms.write'
      allowedMemberTypes: ['Application']
      displayName: 'Agent: leads and small discounts'
      description: 'Lets an agent identity create leads and apply small discounts.'
      isEnabled: true
    }
    {
      id: roleManagerId
      value: 'dms.manager'
      allowedMemberTypes: ['User']
      displayName: 'Sales manager'
      description: 'Big discounts and deleting leads. Never assigned to agents.'
      isEnabled: true
    }
  ]
}

resource sp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: app.appId
}

resource managerAssignment 'Microsoft.Graph/appRoleAssignedTo@v1.0' = if (!empty(managerPrincipalId)) {
  appRoleId: roleManagerId
  principalId: managerPrincipalId
  resourceId: sp.id
}

// Agents get read + write. There is deliberately no loop that grants dms.manager.
resource agentRead 'Microsoft.Graph/appRoleAssignedTo@v1.0' = [for id in agentPrincipalIds: {
  appRoleId: roleReadId
  principalId: id
  resourceId: sp.id
}]

resource agentWrite 'Microsoft.Graph/appRoleAssignedTo@v1.0' = [for id in agentPrincipalIds: {
  appRoleId: roleWriteId
  principalId: id
  resourceId: sp.id
}]

output clientId string = app.appId
output servicePrincipalId string = sp.id
output roleReadId string = roleReadId
output roleWriteId string = roleWriteId
