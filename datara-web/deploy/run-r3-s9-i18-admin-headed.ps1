$ErrorActionPreference = 'Stop'
# R3-S9 #2 人工确认闸：headed admin launcher（操作约定）
#
# 用途：在真实 UI 完成剩余的"人工确认导入"步骤 — headed 浏览器由本脚本拉起，
#       人工在页面输入摘要绑定确认语并点击导入按钮；自动化不代输、不点击、不调用 import。
#
# 安全约定（合同冻结于 test_r3_s9_legacy_preview_page.py；Codex 返工裁定：stdin 或等价短时本地 IPC）：
#   1. admin token 仅由人工在本机经 Read-Host -AsSecureString 输入（不回显、不落盘）；
#   2. token 经 stdin 单向管道（本地 IPC）传给 runner 子进程 — 不进 argv、不进环境变量、
#      不落盘；全程无托管字符串副本（SecureString → BSTR → 可清零字节缓冲 → stdin）；
#      缓冲清理不依赖单一退出路径：SecureString/BSTR/UTF-16 转换后立即在 finally 清零，
#      UTF-8 缓冲由覆盖"进程启动 → stdin 写入"全程的外层 finally 清零（Codex 二审缺口回归）；
#   3. token 仅经 playwright addInitScript 注入当前页面内存（window.__DATARA_TEST_TOKEN__），
#      不进 URL / DOM 属性 / localStorage/sessionStorage / 日志 / 证据 JSON / 仓库；
#      runner 侧另有泄漏闸（fail-closed）：argv/环境变量/证据/stdout 任一面出现 token 即拒绝记录证据；
#   4. token 应为短时凭据（建议 TTL ≤ 10 分钟），由 1.9 root-only 持久 admin store 换出。
# 前置：已获用户批准执行人工确认闸；token 由授权运维/人工本人提供（本脚本不索取、不存储凭据）。

$secure = Read-Host -Prompt '输入短时 admin token（输入不回显）' -AsSecureString
$ptr = [IntPtr]::Zero
$utf16 = $null
$utf8 = $null
try {
    # BSTR 转换在 try 内（Codex 复审缺口回归）：SecureStringToBSTR/字节复制/编码转换任何一步抛出，
    # finally 都会执行 — 有条件清零非零 BSTR 指针 + 无条件释放 SecureString。
    $ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    # BSTR 长度前缀在指针前 4 字节（字节数）；直接按字节复制，绝不物化托管字符串
    $byteLen = [System.Runtime.InteropServices.Marshal]::ReadInt32($ptr, -4)
    if ($byteLen -gt 0) {
        $utf16 = New-Object byte[] $byteLen
        [System.Runtime.InteropServices.Marshal]::Copy($ptr, $utf16, 0, $byteLen)
        $utf8 = [System.Text.Encoding]::Convert([System.Text.Encoding]::Unicode, [System.Text.Encoding]::UTF8, $utf16)
    }
}
finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [System.Runtime.InteropServices.Marshal]::ZeroBSTR($ptr)
        $ptr = [IntPtr]::Zero
    }
    # SecureString 无条件释放（即使上面的转换失败）
    $secure.Dispose()
    if ($utf16) {
        [System.Array]::Clear($utf16, 0, $utf16.Length)
        $utf16 = $null
    }
}
if (-not $utf8 -or $utf8.Length -eq 0) { throw 'Admin token is required for the headed confirmation gate.' }

# 进程启动到 stdin 写入全程包裹在外层 try/finally：任何一步失败（含 Process.Start 本身），
# UTF-8 缓冲都会被清零，不残留活动凭据字节。
$proc = $null
$exitCode = $null
try {
    # runner 子进程：仅重定向 stdin；stdout/stderr 直接继承控制台（不新增缓存转发面）。
    # 注：直连 node 而非经 rtk 包装 — rtk 的 stdin 转发行为未验证，管道语义必须确定。
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'node'
    $psi.Arguments = "`"$PSScriptRoot\r3-s9-i18-preview.cjs`" --token-stdin"
    $psi.WorkingDirectory = $PSScriptRoot
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false
    # 防御性清除：若上级环境残留旧通道变量，不得带入子进程
    $psi.EnvironmentVariables.Remove('DATARA_REBUILD_ADMIN_TOKEN') | Out-Null
    $psi.EnvironmentVariables['DATARA_REBUILD_BASE_URL'] = 'http://192.168.1.9:18091'
    $edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    if (Test-Path -LiteralPath $edge) {
        $psi.EnvironmentVariables['DATARA_PLAYWRIGHT_EXECUTABLE'] = $edge
    }
    $proc = [System.Diagnostics.Process]::Start($psi)
    # 仅经 BaseStream 写原始字节（绕过 StreamWriter 的托管字符串副本），写毕立即关闭通道。
    $stdin = $proc.StandardInput.BaseStream
    try {
        $stdin.Write($utf8, 0, $utf8.Length)
        $stdin.WriteByte(10)
        $stdin.Flush()
    }
    finally {
        $stdin.Close()
    }
    $proc.WaitForExit()
    $exitCode = $proc.ExitCode
}
finally {
    if ($proc) { $proc.Dispose() }
    [System.Array]::Clear($utf8, 0, $utf8.Length)
    $utf8 = $null
}
if ($exitCode -ne 0) { throw 'R3-S9 headed admin confirmation gate did not pass.' }
