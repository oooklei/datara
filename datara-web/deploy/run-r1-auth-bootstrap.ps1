$ErrorActionPreference = 'Stop'
$remote = 'root@192.168.1.9'
$keyLine = & ssh -o BatchMode=yes $remote "grep '^REBUILD_VALIDATION_KEY=' /lei/datara/.env | cut -d= -f2-"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($keyLine) -or $keyLine -notmatch '^[0-9a-f]{64}$') {
    throw 'Could not obtain the configured R1 validation key from the approved remote runtime.'
}

$env:DATARA_REBUILD_BASE_URL = 'http://192.168.1.9:18091'
$env:DATARA_REBUILD_VALIDATION_KEY = $keyLine
$keyLine = $null
try {
    rtk node "$PSScriptRoot/r1-auth-bootstrap-smoke.cjs"
    if ($LASTEXITCODE -ne 0) { throw 'R1 Playwright control-level validation failed.' }
}
finally {
    Remove-Item Env:DATARA_REBUILD_VALIDATION_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:DATARA_REBUILD_BASE_URL -ErrorAction SilentlyContinue
}
