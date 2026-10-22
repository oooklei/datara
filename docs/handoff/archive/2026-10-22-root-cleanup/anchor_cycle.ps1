$ErrorActionPreference = 'Stop'
# duty cycle 锚定：三源+候收编面
$mb = [System.IO.File]::ReadAllLines('d:\需求\数据治理工具\Datara\docs\handoff\mailbox.jsonl')
$mt = $mb[$mb.Count - 1] | ConvertFrom-Json
Write-Output ("MB {0} L{1}" -f $mt.id, $mb.Count)
$st = [System.IO.File]::ReadAllLines('d:\需求\数据治理工具\Datara\docs\handoff\STATE.md')
Write-Output ("ST {0} L{1}" -f $st[$st.Count - 1].Substring(0, 14), $st.Count)
$cut = Get-Date '2026-10-22 06:10:30'
Write-Output '--- outbox new ---'
Get-ChildItem 'd:\需求\数据治理工具\Datara\docs\handoff\outbox' -Recurse -Filter *.json |
  Where-Object { $_.LastWriteTime -gt $cut -and $_.Directory.Name -ne 'c' } |
  Sort-Object LastWriteTime |
  ForEach-Object { '{0} {1} {2}' -f $_.LastWriteTime.ToString('HH:mm:ss'), $_.Directory.Name, $_.Name }
Write-Output '--- handoff-results new ---'
Get-ChildItem 'D:\super-develop\runtime\datara-live\handoff-results' -Filter *.json |
  Where-Object { $_.LastWriteTime -gt $cut } |
  Sort-Object LastWriteTime |
  ForEach-Object { '{0} {1}' -f $_.LastWriteTime.ToString('HH:mm:ss'), $_.Name }
Write-Output '--- git short ---'
git -C 'd:\需求\数据治理工具\Datara' status --porcelain=v1 | Measure-Object -Line | ForEach-Object { "dirty_lines=$($_.Lines)" }
git -C 'd:\需求\数据治理工具\Datara' log --oneline -1
Write-Output 'ANCHOR_DONE'
