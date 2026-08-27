// ============================================================================
// Recover — Azure infrastructure.
//
//   • Azure Container Registry
//   • Log Analytics workspace + Application Insights
//   • Azure Container Apps environment
//   • Key Vault, with the backend's managed identity granted read on it
//   • Two Container Apps: frontend and backend
//
// Idempotent: re-running updates in place. CI never touches this file — it
// only swaps container images — so a Bicep change means re-running
// infra/setup-azure.sh.
//
// Redis is dropped for now (see README §Cost, "Drop Redis until the phase
// that needs it"): nothing in the backend reads REDIS_URL yet, and
// Microsoft.Cache/redis (classic Azure Cache for Redis) is retired for new
// deployments in some regions/subscriptions — az deployment fails with
// "Azure Cache for Redis is retiring, create Azure Managed Redis instance
// instead." Re-add it as Microsoft.Cache/redisEnterprise (Azure Managed
// Redis) when a phase actually needs a cache; that resource has a different
// shape (a cluster plus a `databases` child resource, different key/host
// properties) so it is not a drop-in swap of the api version here.
// ============================================================================

@description('Short prefix, lowercase. Capped at 12 because the Key Vault name is derived from it and Azure allows 24 characters for that.')
@minLength(3)
@maxLength(12)
param namePrefix string

@description('Environment name: prod, staging, etc.')
param environment string = 'prod'

@description('Azure region')
param location string = resourceGroup().location

@description('Placeholder image for the initial Container App create. CI replaces it with a real, commit-tagged image on the first deploy.')
param placeholderImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Supabase project URL. Public — it is in the browser bundle.')
param supabaseUrl string

@description('Supabase anon key. Public — it is in the browser bundle, and RLS is what protects the data.')
param supabaseAnonKey string

@description('Overrides the frontend origin used for the backend CORS allowlist. Leave empty to use the Container App FQDN, which this template computes; set it when the frontend is behind a custom domain.')
param frontendUrlHint string = ''

var tags = {
  project: 'recover'
  environment: environment
}

// Resource names, all derived from prefix + environment.
var acrName          = replace('${namePrefix}${environment}acr', '-', '')
var logAnalyticsName = '${namePrefix}-${environment}-logs'
var appInsightsName  = '${namePrefix}-${environment}-ai'
var envName          = '${namePrefix}-${environment}-env'
var kvName           = '${namePrefix}-${environment}-kv'
var backendAppName   = '${namePrefix}-${environment}-backend'
var frontendAppName  = '${namePrefix}-${environment}-frontend'
var backendUAMIName  = '${namePrefix}-${environment}-be-uami'
var frontendUAMIName = '${namePrefix}-${environment}-fe-uami'

// ==================== Container Registry ====================
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    // The Container Apps pull identity is the admin credential, referenced
    // below as a secret. A managed identity pull is tidier, but it needs an
    // AcrPull assignment that has to exist before the first revision starts.
    adminUserEnabled: true
  }
}

// ==================== Log Analytics + Application Insights ====================
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
}

// ==================== User-assigned managed identities ====================
// One per app rather than one shared, so the frontend identity can never be
// granted vault access by accident: only the backend reads secrets.
resource backendUAMI 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: backendUAMIName
  location: location
  tags: tags
}

resource frontendUAMI 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: frontendUAMIName
  location: location
  tags: tags
}

// ==================== Key Vault ====================
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    // RBAC rather than access policies: the role assignment below is then the
    // single, greppable statement of who can read what.
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    // Purge protection is deliberately left unset. Once enabled it cannot be
    // turned off, and it blocks reusing this vault name for the retention
    // window — an expensive thing to discover on a hackathon timeline.
    publicNetworkAccess: 'Enabled'
  }
}

// Key Vault Secrets User — read secret values, nothing else.
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // Deterministic name, so a re-run updates the same assignment rather than
  // colliding with itself.
  name: guid(kv.id, backendUAMI.id, keyVaultSecretsUserRoleId)
  scope: kv
  properties: {
    principalId: backendUAMI.properties.principalId
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Seeded secrets. The two Supabase public values come from parameters; the
// genuinely secret ones are seeded as REPLACE_ME and set out of band, so no
// real credential is ever in this repository or in a deployment history.
//
// The corollary, and it bites: **every deployment resets these three to
// REPLACE_ME.** That is the cost of keeping them out of the deployment history
// — a `@secure()` param would survive redeploys but would put the value in the
// ARM deployment record, which is the thing this design refuses. So after any
// `az deployment group create`, re-run the three `az keyvault secret set`
// commands and restart the backend revision, or it will boot with placeholder
// credentials: Supabase auth fails closed, and GEMINI_API_KEY being a
// non-empty non-key means every LLM step quietly returns its fallback.
resource kvSecretSupabaseUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'supabase-url'
  properties: {
    value: supabaseUrl
  }
}

resource kvSecretSupabaseAnon 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'supabase-anon-key'
  properties: {
    value: supabaseAnonKey
  }
}

resource kvSecretSupabaseService 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'supabase-service-key'
  properties: {
    value: 'REPLACE_ME'
  }
}

resource kvSecretSupabaseJwt 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'supabase-jwt-secret'
  properties: {
    value: 'REPLACE_ME'
  }
}

resource kvSecretGeminiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'gemini-api-key'
  properties: {
    value: 'REPLACE_ME'
  }
}

// ==================== Container Apps environment ====================
resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// An external-ingress app's FQDN is always <appName>.<environment defaultDomain>,
// which is known as soon as the environment exists. Computing it here means the
// backend's CORS allowlist is correct on the first deployment, instead of
// needing a second pass once the frontend URL can be read back.
var frontendUrl = empty(frontendUrlHint)
  ? 'https://${frontendAppName}.${containerAppsEnv.properties.defaultDomain}'
  : frontendUrlHint

// ==================== Backend Container App ====================
resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${backendUAMI.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        // No corsPolicy here on purpose. The ingress is Envoy, and its CORS
        // filter would append Access-Control-Allow-Origin to a response
        // FastAPI's CORSMiddleware has already set it on — two identical
        // headers, which every browser rejects. CORS has exactly one owner in
        // this stack: the ALLOWED_ORIGINS env var below.
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'supabase-url'
          keyVaultUrl: kvSecretSupabaseUrl.properties.secretUri
          identity: backendUAMI.id
        }
        {
          name: 'supabase-anon-key'
          keyVaultUrl: kvSecretSupabaseAnon.properties.secretUri
          identity: backendUAMI.id
        }
        {
          name: 'supabase-service-key'
          keyVaultUrl: kvSecretSupabaseService.properties.secretUri
          identity: backendUAMI.id
        }
        {
          name: 'supabase-jwt-secret'
          keyVaultUrl: kvSecretSupabaseJwt.properties.secretUri
          identity: backendUAMI.id
        }
        {
          name: 'gemini-api-key'
          keyVaultUrl: kvSecretGeminiKey.properties.secretUri
          identity: backendUAMI.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: placeholderImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'ENVIRONMENT'
              value: 'production'
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
            {
              name: 'VERSION'
              value: '0.3.0'
            }
            {
              name: 'ALLOWED_ORIGINS'
              value: frontendUrl
            }
            {
              name: 'SUPABASE_URL'
              secretRef: 'supabase-url'
            }
            {
              name: 'SUPABASE_ANON_KEY'
              secretRef: 'supabase-anon-key'
            }
            {
              name: 'SUPABASE_SERVICE_KEY'
              secretRef: 'supabase-service-key'
            }
            {
              name: 'SUPABASE_JWT_SECRET'
              secretRef: 'supabase-jwt-secret'
            }
            {
              name: 'GEMINI_API_KEY'
              secretRef: 'gemini-api-key'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsights.properties.ConnectionString
            }
          ]
          probes: [
            {
              // /health answers from process state alone — no Supabase call —
              // so a Supabase outage cannot get healthy replicas killed.
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              periodSeconds: 10
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        // minReplicas 1, not 0: scale-to-zero would put a cold start in front
        // of the first request of every demo.
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '30'
              }
            }
          }
        ]
      }
    }
  }
  // Bicep infers dependencies from symbolic references, and nothing above
  // references the role assignment. Without this the app can be created before
  // its identity may read the vault, and the first revision fails to start on
  // an unresolvable secret reference.
  dependsOn: [
    kvRoleAssignment
  ]
}

// ==================== Frontend Container App ====================
resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${frontendUAMI.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: placeholderImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          // No NEXT_PUBLIC_* here. Next inlines those into the browser bundle
          // at build time; setting them as runtime env vars would have no
          // effect on what the browser actually loads. They are build args in
          // the workflow instead.
          env: [
            {
              name: 'NODE_ENV'
              value: 'production'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/'
                port: 3000
              }
              periodSeconds: 30
              failureThreshold: 3
              initialDelaySeconds: 20
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
}

// ==================== Outputs ====================
output acrLoginServer string           = acr.properties.loginServer
output acrName string                  = acr.name
output backendFqdn string              = backendApp.properties.configuration.ingress.fqdn
output frontendFqdn string             = frontendApp.properties.configuration.ingress.fqdn
output keyVaultName string             = kv.name
output appInsightsName string          = appInsights.name
output backendContainerAppName string  = backendApp.name
output frontendContainerAppName string = frontendApp.name
output backendUAMIClientId string      = backendUAMI.properties.clientId
output frontendUAMIClientId string     = frontendUAMI.properties.clientId
