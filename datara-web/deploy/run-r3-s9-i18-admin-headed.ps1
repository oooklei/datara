$ErrorActionPreference = 'Stop'
# R3-S9 #2 人工确认闸：headed admin launcher（操作约定）
#
# 用途：在真实 UI 完成剩余的"人工确认导入"步骤 — headed 浏览器由本脚本打开，
#       人工在页面输入摘要绑定确认语并点击导入按钮；自动化不代输、不点击、不调用 import。
#
# 安全约定（合同冻结于 test_r3_s9_legacy_preview_page.py）：
#   1. admin token 仅由人工在本机经 Read-Host -AsSecureString 输入（不回显、不落盘）；
#   2. token 仅经 playwright addInitScript 注入当前页面内存（window.__DATARA_TEST_TOKEN__），
#      不进 URL / DOM 属性 / localStorage/sessionStorage / 日志 / 证据 JSON / 仓库；
#   3. token 应为短时凭据（建议 TTL ≤ 10 分钟），由 1.9 root-only 持久 admin store 换出；
#   4. 脚本退出时 token 从进程环境清除；SecureString 缓冲区即时归零。
# 前置：已获用户批准执行人工确认闸；token 由授权运维/人工本人提供（本脚本不索取、不存储凭据）。

$secure = Read-Host -Prompt '输入短时 admin token（输入不回显）' -AsSecureString
$ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $token = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
}
finally {
    [System.Runtime.InteropServices.Marshal]::ZeroBSTR($ptr)
    $ptr = $null
}
if ([string]::IsNullOrWhiteSpace($token)) { throw 'Admin token is required for the headed confirmation gate.' }

$env:DATARA_REBUILD_BASE_URL = 'http://192.168.1.9:18091'
$env:DATARA_REBUILD_ADMIN_TOKEN = $token
$token = $null
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (Test-Path -LiteralPath $edge) {
    $env:DATARA_PLAYWRIGHT_EXECUTABLE = $edge
}
try {
    rtk node "$PSScriptRoot/r3-s9-i18-preview.cjs"
    if ($LASTEXITCODE -ne 0) { throw 'R3-S9 headed admin confirmation gate did not pass.' }
}
finally {
    Remove-Item Env:DATARA_REBUILD_ADMIN_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:DATARA_REBUILD_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:DATARA_PLAYWRIGHT_EXECUTABLE -ErrorAction SilentlyContinue
}
