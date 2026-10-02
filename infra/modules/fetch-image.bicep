// Returns the image a container app currently runs, so re-provisioning never
// rolls an app back to the placeholder. Lives in its own module (its own
// deployment), otherwise reading and writing the same app is a circular dependency.
param name string
param exists bool

resource app 'Microsoft.App/containerApps@2025-07-01' existing = if (exists) {
  name: name
}

output image string = exists ? app!.properties.template.containers[0].image : ''
