param(
  [Parameter(Mandatory = $true)]
  [string]$BackendUrl
)

$ErrorActionPreference = "Stop"
$normalizedBackendUrl = $BackendUrl.TrimEnd("/")

Write-Host "Checking Product-to-MCP backend:" $normalizedBackendUrl

$health = Invoke-RestMethod -Method Get -Uri "$normalizedBackendUrl/healthz"
Write-Host "healthz:" ($health | ConvertTo-Json -Compress)

$ready = Invoke-RestMethod -Method Get -Uri "$normalizedBackendUrl/readyz"
Write-Host "readyz:" ($ready | ConvertTo-Json -Compress)

if ($ready.public_base_url_https -ne "true") {
  Write-Warning "PRODUCT_TO_MCP_PUBLIC_BASE_URL is not HTTPS. Smithery publishing will stay disabled."
}

if ($ready.database -ne "ok") {
  throw "Backend database readiness check failed."
}

Write-Host "Deployment smoke check passed."
