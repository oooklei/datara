$ErrorActionPreference = 'Stop'
$stPath = 'D:\需求\数据治理工具\Datara\docs\handoff\STATE.md'
$arPath = 'D:\需求\数据治理工具\Datara\docs\handoff\archive\2026-10-22-STATE-S303.md'

$lines = [System.IO.File]::ReadAllLines($stPath)
if ($lines.Count -gt 60) { throw "PRE_GUARD_FAIL: 行数 $($lines.Count) >60" }
if (-not $lines[$lines.Count-1].Contains('S309 |')) { throw "TAIL_GUARD_FAIL: 尾行非 S309" }
Write-Output ("PRE_OK lines={0} tail=S309" -f $lines.Count)

# 定位 S303 行
$s303Idx = @()
for ($i=0; $i -lt $lines.Count; $i++) { if ($lines[$i].Contains('S303 |')) { $s303Idx += $i } }
if ($s303Idx.Count -ne 1) { throw "S303_LOCATE_FAIL: 命中 $($s303Idx.Count) 处" }
$s303Text = $lines[$s303Idx[0]]

# archive 幂等写入
if (Test-Path $arPath) {
  $exist = Get-Content $arPath -Raw
  if (-not $exist.Contains('S303 | 监督员C')) { throw "ARCHIVE_EXISTS_DIFF" }
  Write-Output "ARCHIVE_EXISTS_IDEMPOTENT"
} else {
  $hdr = "# STATE S303 原文（2026-10-22 C 迁出腾位）`n`n"
  [System.IO.File]::WriteAllText($arPath, $hdr + $s303Text + "`n", (New-Object System.Text.UTF8Encoding($false)))
  Write-Output "ARCHIVE_WRITTEN"
}

# 删 S303 行
$newLines = New-Object System.Collections.Generic.List[string]
for ($i=0; $i -lt $lines.Count; $i++) { if ($i -ne $s303Idx[0]) { $newLines.Add($lines[$i]) } }

# 构造 S310 行
$s310 = 'S310 | C_CONTROLLER | 2026-10-22 06:45 Asia/Shanghai（C 席 epoch=2 第四轮 duty cycle ROUND=4；查重 S310 零命中取号，尾行断言 S309；mailbox 368 行尾=s375；S303 原文迁 archive/2026-10-22-STATE-S303.md 腾位） | 收编 4 件（RT 项 RELEASED+V2 批1 采信 PASS+P2 第十票+B-ESC-01 销项）+二切片/AUTH-01 解锁+claude 三披露处置（s375 落箱） | ①cl-report-llm-01-fe-node-b-evidence 采信：RT-LLM-01-FE-EVIDENCE 执行收口 EVIDENCE_READY→RELEASED（执行席沿 s369/s370 先例自裁候 V2 复核终局）；C 初核 PASS=RED 真实（06:14:02 固定字面量误断言 4091vs4092 非编译错非空洞，空洞初版废弃在证据外）+GREEN 06:14:16 5 passed 同工作区同命令+双探针 401/405+evidence 十字段落档 /lei/datara-newweb-iso/evidence/llm-models/ 5 件带 sha256（证据窗 06:13:17~06:14:41 1.9 实测）；②validation-v2-current-batch 采信（分担授权 delegation-activation-1 终写归 C）：batch1-7c6d916-ratify PASS 六检查全过（恰件4+行数对账+元信息+零漂移+历史链绑定+去重）→V2_RESULT_ACCEPTABLE 门证据留档；s374【三】V2 队列卡四项全闭环（批1 PASS+AUDIT-01 ②③④ 收位 seq9+DB-token-02 r1 收位 seq11+预审 4 件=42 PASS/43 REWORK 候补件/两 cl-report PASS）；validation queue→EMPTY；闸门效应=DB-token-02 二切片+AUTH-01 放行候 trae 单会话串行排程；③P2 第十票 PROJ-FE-01-R2 收编（v7 gatekeeper PASS，票仓 PRODUCED_READY 候位次 DR-10 扩展两 R2 票并登）；dispatch-p2-current 06:14 重读=校准基底无新内容；④a-main-b-esc-01-resolution 收编=B-ESC-01 销项（bd2e0589 Next run 渲染层异常非阻塞维持现状）；scheduler 四 Active 全景登记（ed71be88/bd2e0589/1acc2ab6/a98f691d）+托管双件撤销干净；⑤claude 信三项披露处置：双工作区引用位裁定=/lei/datara-newweb-iso/datara-newweb（claim 承诺路径+三关键件 sha256 逐字节一致；testws/llm-fe-ws 保留候 I1/用户不清理）+单写者澄清（s373/s374 系本席 epoch=2 依序所写无并发第二 C；claude 直写两次被 append-only 守卫正确拦停零写入改走 outbox 通道处置正确；DR-7 残项=loop 会话历史违例追认候裁不变）+终端池只读命令=V2 会话 commands_run 吻合判合规非注入；⑥队列卡：trae=二切片解锁候开工（ack 起算 30min 沿 tr-ack-34 先例）次 NEXT=AUTH-01 同队列串行+tr-done-43 REWORK 补件义务；claude=节点 B 收口摘 PROJ-FE-01（用户裁下一票）；V2=RT-LLM-01-FE-EVIDENCE RELEASED 复核确认；P2=iteration11 候消费 s375；B=DR-3/7/8 候裁维持；⑦循环治理：*/15 recurring 哨兵循环依用户令建立，ed71be88（*/30）冗余 pause 披露保留可恢复；⑧合规：主会话 1 席+子智能体 0（ROUND=4 空转比 0）；AOCI 零调用；下一取号 s376。'
$newLines.Add($s310)

# 复验行数与尾行
if ($newLines.Count -gt 60) { throw "POST_GUARD_FAIL: 行数 $($newLines.Count) >60" }
if (-not $newLines[$newLines.Count-1].Contains('S310 |')) { throw "S310_FORMAT_FAIL" }

# 写回
[System.IO.File]::WriteAllLines($stPath, $newLines, (New-Object System.Text.UTF8Encoding($false)))
$verify = [System.IO.File]::ReadAllLines($stPath)
Write-Output ("POST_OK lines={0} tail=S310" -f $verify.Count)
if ($verify.Count -ne $newLines.Count) { throw "WRITE_VERIFY_FAIL" }
