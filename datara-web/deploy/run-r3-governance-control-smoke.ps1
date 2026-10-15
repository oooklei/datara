# R3 governance control smoke launcher（headless，受保护 runner 路径）。
# 从 1.9 root-only .env 读取 REBUILD_VALIDATION_KEY，仅注入本进程环境；
# 子进程环境中不携带 key（finally 中显式移除），token 只经 addInitScript 进入页面内存。
$ErrorActionPreference = 'Stop'
$remote = 'root@192.168.1.9'
$keyLine = & ssh -o BatchMode=yes $remote "grep '^REBUILD_VALIDATION_KEY=' /lei/datara/.env | cut -d= -f2-"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($keyLine) -or $keyLine -notmatch '^[0-9a-f]{64}$') {
    throw 'Could not obtain the configured governance validation key from the approved remote runtime.'
}

$env:DATARA_REBUILD_BASE_URL = 'http://192.168.1.9:18091'
$env:DATARA_REBUILD_VALIDATION_KEY = $keyLine
$keyLine = $null
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (Test-Path -LiteralPath $edge) {
    $env:DATARA_PLAYWRIGHT_EXECUTABLE = $edge
}
try {
    rtk node "$PSScriptRoot/r3-governance-control-smoke.cjs"
    if ($LASTEXITCODE -ne 0) { throw 'R3 governance control smoke validation did not pass.' }
}
finally {
    Remove-Item Env:DATARA_REBUILD_VALIDATION_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:DATARA_REBUILD_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:DATARA_PLAYWRIGHT_EXECUTABLE -ErrorAction SilentlyContinue
}
