param(
  [string]$BaseUrl = 'http://192.168.1.9:18091/api/v1',
  [string]$EnvPath = 'D:\需求\数据治理工具\Datara\datara-backend\.env'
)

$ErrorActionPreference = 'Stop'
$values = @{}
Get-Content -LiteralPath $EnvPath | ForEach-Object {
  if ($_ -match '^(LLM_PROVIDER|LLM_BASE_URL|LLM_MODEL|LLM_API_KEY)=(.*)$') {
    $values[$matches[1]] = $matches[2].Trim()
  }
}
foreach ($required in 'LLM_BASE_URL','LLM_MODEL','LLM_API_KEY') {
  if ([string]::IsNullOrWhiteSpace($values[$required])) { throw "Missing $required" }
}

$loginBody = @{ username = 'admin'; password = 'Admin@123' } | ConvertTo-Json -Compress
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/rebuild/login" -ContentType 'application/json' -Body $loginBody
$token = $login.data.token
$headers = @{ token = $token }
$existing = Invoke-RestMethod -Method Get -Uri "$BaseUrl/rebuild/llm-models?offset=0&limit=50" -Headers $headers
$model = @($existing.data.items) | Where-Object { $_.provider -eq 'longcat' } | Select-Object -First 1
$longcatApiBase = $values.LLM_BASE_URL.TrimEnd('/')
if (-not $longcatApiBase.EndsWith('/v1')) { $longcatApiBase = "$longcatApiBase/v1" }
$payload = @{
  name = 'longcat-default'
  display_name = 'LongCat 2.5 Preview'
  provider = 'longcat'
  api_base = $longcatApiBase
  model_id = $values.LLM_MODEL
  api_key = $values.LLM_API_KEY
  max_tokens = 10000
  temperature = 0.7
  is_active = $true
  is_default = $true
  sort_order = 0
} | ConvertTo-Json -Compress

if ($null -eq $model) {
  $saved = Invoke-RestMethod -Method Post -Uri "$BaseUrl/rebuild/llm-models" -Headers $headers -ContentType 'application/json' -Body $payload
  $action = 'created'
} else {
  $saved = Invoke-RestMethod -Method Put -Uri "$BaseUrl/rebuild/llm-models/$($model.id)" -Headers $headers -ContentType 'application/json' -Body $payload
  $action = 'updated'
}
$modelId = $saved.data.id
$probeStatus = 'not-run'
$probeMessage = ''
try {
  $probe = Invoke-RestMethod -Method Post -Uri "$BaseUrl/rebuild/llm-models/$modelId/test" -Headers $headers -ContentType 'application/json'
  $probeStatus = if ($probe.data.status -eq 'success') { 'ok' } else { 'failed' }
  $probeMessage = [string]$probe.data.message
} catch {
  $probeStatus = 'failed'
  $probeMessage = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
}
$after = Invoke-RestMethod -Method Get -Uri "$BaseUrl/rebuild/llm-models?offset=0&limit=50" -Headers $headers
[pscustomobject]@{
  action = $action
  count = @($after.data.items).Count
  id = $modelId
  provider = $saved.data.provider
  model = $saved.data.model_id
  active = $saved.data.is_active
  default = $saved.data.is_default
  probe = $probeStatus
  probeMessage = $probeMessage
} | ConvertTo-Json -Compress
