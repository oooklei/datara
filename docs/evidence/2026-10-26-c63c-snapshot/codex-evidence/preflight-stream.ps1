$p = (Get-Process codex -ErrorAction SilentlyContinue | Measure-Object).Count
$locks = (Get-ChildItem -LiteralPath "C:\Users\Administrator\.codex" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "\.(lock|lck)$" } |
    Measure-Object).Count
[pscustomobject]@{
    codex_processes = $p
    session_lock_files = $locks
    action = "report-only-no-cleanup"
} | ConvertTo-Json -Compress
