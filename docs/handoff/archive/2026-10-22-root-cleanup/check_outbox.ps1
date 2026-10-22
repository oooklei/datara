$ErrorActionPreference = 'Stop'
$out = 'd:\需求\数据治理工具\Datara\check_outbox_result.txt'
$sb = New-Object System.Collections.Generic.List[string]
$ob = 'D:\需求\数据治理工具\Datara\docs\handoff\outbox'
$sb.Add("=== queues ===")
Get-ChildItem $ob -Directory | ForEach-Object { $sb.Add($_.Name) }
$sb.Add("=== all queues newest 5 each ===")
Get-ChildItem $ob -Directory | ForEach-Object {
  $q = $_.Name
  Get-ChildItem $_.FullName -Filter *.json | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object { $sb.Add("[$q] " + $_.LastWriteTime.ToString('HH:mm:ss') + " " + $_.Name) }
}
$sb.Add("=== files newer than 06:10 today across queues ===")
Get-ChildItem $ob -Recurse -Filter *.json | Where-Object { $_.LastWriteTime -ge (Get-Date '2026-10-22 06:10:00') } | Sort-Object LastWriteTime | ForEach-Object { $sb.Add($_.LastWriteTime.ToString('HH:mm:ss') + " [" + $_.Directory.Name + "] " + $_.Name) }
[System.IO.File]::WriteAllLines($out, $sb, (New-Object System.Text.UTF8Encoding($false)))
