# §10.7 海豚集成验收入口：取短时验证 token 后调用 verify-ds-embed-browser.cjs。
# 客户观摩入口固定 192.168.1.9:8090；token 仅内存传递，不落盘、不入 URL。
$ErrorActionPreference = 'Stop'
$base = 'http://192.168.1.9:8090'
$projectId = if ($args.Count -ge 1) { $args[0] } else { 33 }

$remoteKey = (& ssh -o BatchMode=yes -o ConnectTimeout=5 192.168.1.9 'docker exec datara-rebuild-api printenv REBUILD_VALIDATION_KEY').Trim()
if (-not $remoteKey) { throw 'validation key unavailable on backend' }
$response = Invoke-RestMethod -Method Post -Uri "$base/api/v1/rebuild/validation-token" -Headers @{
    'X-Backend-Validation-Key' = $remoteKey
    'X-Backend-Validation-Scope' = 'high-priority-e2e'
}
$remoteKey = $null
if (-not $response.data.token) { throw 'short-lived token exchange failed' }
$env:DATARA_DS_VERIFY_TOKEN = $response.data.token
try {
    & node 'deploy/wsl-frontend/verify-ds-embed-browser.cjs' $base $projectId
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Remove-Item Env:DATARA_DS_VERIFY_TOKEN -ErrorAction SilentlyContinue
}
