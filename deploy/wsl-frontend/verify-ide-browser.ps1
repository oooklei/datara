$ErrorActionPreference = 'Stop'
$base = if ($env:DATARA_IDE_VERIFY_BASE) { $env:DATARA_IDE_VERIFY_BASE } else { 'http://192.168.1.9:18091' }
$remoteKey = (& ssh -o BatchMode=yes -o ConnectTimeout=5 192.168.1.9 'docker exec datara-rebuild-api printenv REBUILD_VALIDATION_KEY').Trim()
if (-not $remoteKey) { throw 'validation key unavailable on backend' }
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/rebuild/validation-token" -Headers @{
    'X-Backend-Validation-Key' = $remoteKey
    'X-Backend-Validation-Scope' = 'high-priority-e2e'
}
$remoteKey = $null
if (-not $response.data.token) { throw 'short-lived token exchange failed' }
$env:DATARA_IDE_VERIFY_TOKEN = $response.data.token
try {
    & node 'deploy/wsl-frontend/verify-ide-browser.cjs'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Remove-Item Env:DATARA_IDE_VERIFY_TOKEN -ErrorAction SilentlyContinue
}
