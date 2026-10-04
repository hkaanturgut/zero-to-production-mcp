// The MCP API on the gateway: a transparent proxy for /mcp, the Protected
// Resource Metadata and /healthz. Callers authenticate with their Entra token,
// which the MCP server validates; the gateway adds the shared rate limit.
param apimName string
param backendUrl string
@description('Calls allowed per caller per minute, across all replicas.')
param callsPerMinute int = 120

resource apim 'Microsoft.ApiManagement/service@2024-05-01' existing = {
  name: apimName
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'dealer-mcp'
  properties: {
    displayName: 'Dealer MCP server'
    path: '' // the gateway root, so /mcp and /.well-known/... keep their paths
    protocols: ['https']
    serviceUrl: backendUrl
    subscriptionRequired: false // the Entra token is the credential, not an APIM key
  }
}

resource operations 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = [
  for method in ['GET', 'POST', 'DELETE']: {
    parent: api
    name: 'all-${toLower(method)}'
    properties: {
      displayName: '${method} /*'
      method: method
      urlTemplate: '/*'
    }
  }
]

// Rate-limit key: the caller's object ID from the bearer token (unvalidated here,
// only used as a counter key; the server validates it). Anonymous calls are
// counted per client IP. buffer-response=false keeps streamed responses flowing.
resource policy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: {
    format: 'rawxml'
    value: replace(policyXml, '{{CALLS}}', string(callsPerMinute))
  }
}

// Multi-line strings don't interpolate, so the limit is substituted above.
var policyXml = '''
<policies>
  <inbound>
    <base />
    <set-variable name="caller" value="@{
      var jwt = context.Request.Headers.GetValueOrDefault(&quot;Authorization&quot;, &quot;&quot;).AsJwt();
      var oid = jwt?.Claims.GetValueOrDefault(&quot;oid&quot;, jwt?.Subject);
      return string.IsNullOrEmpty(oid) ? &quot;ip:&quot; + context.Request.IpAddress : oid;
    }" />
    <rate-limit-by-key calls="{{CALLS}}" renewal-period="60" counter-key="@((string)context.Variables[&quot;caller&quot;])" />
  </inbound>
  <backend>
    <forward-request timeout="120" buffer-response="false" />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
'''
