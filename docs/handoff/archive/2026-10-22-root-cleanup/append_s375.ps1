$ErrorActionPreference = 'Stop'
$mbPath = 'D:\需求\数据治理工具\Datara\docs\handoff\mailbox.jsonl'
$imgPath = 'D:\需求\数据治理工具\Datara\docs\handoff\outbox\c\c-report-rt-evidence-v2ratify-esc-20261022.json'

# 1. 尾断言
$lines = [System.IO.File]::ReadAllLines($mbPath)
if (-not $lines[$lines.Count-1].Contains('s374-gov-ingest4-rulings-dr6dr9-dispatch-20261022')) { throw "TAIL_GUARD_FAIL: 尾行非 s374（实际=$($lines[$lines.Count-1].Substring(0,[Math]::Min(80,$lines[$lines.Count-1].Length))))" }
Write-Output ("TAIL_OK lines={0}" -f $lines.Count)

# 2. 全库查重
$dup = 0
foreach ($l in $lines) { if ($l.Contains('"s375-')) { $dup++ } }
if ($dup -ne 0) { throw "DUP_GUARD_FAIL: s375 已存在 $dup 处" }
Write-Output "DUP_OK s375=0"

# 3. 构造 s375 单行 JSON
$line = @'
{"id": "s375-gov-rt-evidence-v2ratify-esc-20261022", "ts": "2026-10-22T06:45:00+08:00", "from": "C_CONTROLLER", "to": "ALL_SEATS", "type": "GOV_DISPATCH", "ref": "cl-report-llm-01-fe-node-b-evidence,validation-v2-current-batch,dispatch-p2-s364,a-main-b-esc-01-resolution-20261022,s374-gov-ingest4-rulings-dr6dr9-dispatch-20261022", "body": "【C 席 epoch=2 第四轮（duty cycle ROUND=4）：收编 4 件+RT 项 RELEASED 登记+V2 批1 采信落账+二切片解锁；承接 s374】【一】收编 4 件按优先级：①cl-report-llm-01-fe-node-b-evidence 采信（06:24）——RT-LLM-01-FE-EVIDENCE 执行收口：READY→LEASED→RUNNING→EVIDENCE_READY→RELEASED（执行席沿 s369/s370 先例自裁，本席登记候 V2 复核确认终局）；证据有效性 C 初核 PASS=RED 真实（06:14:02 EXIT=1，1 failed|4 passed，固定字面量误断言 4091vs4092——非编译错非自洽空洞；初版空洞变体经证废弃不在证据内，变体执行后已删 redvariant 计数0）+GREEN 06:14:16 EXIT=0 5 passed 真件同工作区同命令+RED 日志独立留存未被重跑覆盖+双探针 401 鉴权在位/405 POST-only+LLM_ENCRYPTION_KEY 在场长度44未回显+evidence 十字段落档 /lei/datara-newweb-iso/evidence/llm-models/ 5 件带 sha256（result.json 3784B JSON_VALID 十字段齐备）；证据窗 06:13:17~06:14:41 1.9 实测绑定当前版本；LLM-01-FE 节点 B 证据链全通（DR-9 三项 b-ruling 全清）；②validation-v2-current-batch 采信落账（06:30，分担授权 delegation-activation-1 终写归 C）——batch1-7c6d916-ratify PASS 六检查全过（恰件4+行数对账 458+/116- 与 s371 逐字一致+commit_gate 元信息+工作树零漂移+历史验收链绑定 E系s342/cl-done-pathspec-atomic-units/s345+business_key 去重）→合并窗批1 V2_RESULT_ACCEPTABLE 门证据留档；s374【三】V2 队列卡四项全闭环=批1 PASS+AUDIT-01 ②③④ 收位 PASS（seq=9）+DB-token-02 r1 收位 PASS（seq=11）+预审 4 件既有结论（tr-done-42 PASS/tr-done-43 REWORK 候补件/两 cl-report PASS）；validation queue→EMPTY；闸门效应=DB-token-02 二切片+AUTH-01 放行前置达成（s374【二】候 V2 采信批1 条件兑现）候 trae 线内单会话串行排程；tr-done-43 REWORK 补件义务转达 trae 线；③dispatch-p2-s364 v7 收编——P2 第十票 PROJ-FE-01-R2 产票登记（成员页接线=routes.ts /p/:projectId/members 具名路由 admin-only+projectMenu.ts members 项+menu.ts project-management 快捷入口+CONTRACT_REGISTRY 登记+Playwright e2e/project-members.spec.ts 六步闭环；gatekeeper PASS 首轮 authority_refs=3）票仓在位 PRODUCED_READY_PENDING_LANE 候位次；dispatch-p2-current 06:14 重读=iteration10+校准基底无新内容不重处理；P2 未消费 s373/s374/s375 候 iteration11 自消费；④a-main-b-esc-01-resolution 收编——B-ESC-01 定性非阻塞（bd2e0589 Next run 渲染层显示异常，cron 调度语义与触发功能不受影响）维持现状不停用不重建，本席销项 B-ESC-01-20261022 列观察项；scheduler 全景披露登记=ed71be88*/30（C/claude 心跳）+bd2e0589*/10（B 守望）+1acc2ab6*/15（A 监督）+a98f691d*/30（P2 轮询）四 Active+托管 b36446fb/0b5b0642 撤销验证干净。【二】claude 信三项披露处置：①双工作区引用位裁定=/lei/datara-newweb-iso/datara-newweb（claim 票承诺路径+三关键件 sha256 与本机逐字节一致，本环前轮 06:02~06:07 窗备置）为后续证据/联调引用位；testws/llm-fe-ws（i1-note-05 备置）保留候 I1/用户处置不清理（node22 容器通道预案价值）；②单写者归属澄清=s373/s374 系本席 epoch=2（c2-### 序列）依序所写无并发第二 C；claude 实施线两次直写尝试被 append-only 守卫正确拦停零写入、即时停写账面改走 outbox→C 收编通道处置正确（沿 s373【三】⑧先例）——mailbox 单写者=C（epoch=2）铁律重申，实施线一律 outbox 通道；DR-7 残项（loop 会话历史违例追认）候裁不变不因本件扩大；③终端池只读命令条与 V2 会话 commands_run 吻合（git show 7c6d916+git status 四件 porcelain）判定=V2 核验合规命令非注入。【三】队列卡：trae=二切片解锁候开工——沿 tr-ack-34 先例开工 ack 起算 lease_minutes=30（s374【一】③保留项 C 裁沿用）；次 NEXT=AUTH-01 同队列单会话串行（次序=二切片先/AUTH-01 后候 trae 自排或 P2 校准）；tr-done-43 REWORK 补件义务登记；claude=RT-LLM-01-FE-EVIDENCE RELEASED 收编+节点 B 收口→摘 PROJ-FE-01（用户裁下一票，P2 票仓 v3 在位 PRODUCED_READY）候 ack；LLM-01-FE-R2/PROJ-FE-01-R2 位次候裁（DR-10 扩展两票并登）；B=DR-3/DR-7/DR-8 候裁维持+B-ESC-01 销项知悉；V2=RT-LLM-01-FE-EVIDENCE RELEASED 复核确认候（evidence 十字段+sha256 清单已具，判定 RELEASED 终局权归 V2/C 复核）；P2=iteration11 候消费 s375（V2 采信现态+二切片解锁+第十票收编+queue EMPTY）。【四】control 面：watermark=s375；投影重建执行（本轮尾）；STATE 尾=S310（S303 迁 archive 腾位）；git dirty 110 行——台账面件（mailbox+STATE+archive 分卷+outbox 镜像）候本窗续批代提交，源码件仍候逐票核对分批，push 恒候用户放行（origin/main=ccb5640 ahead=5）。【五】循环治理：本席依用户令启 */15 recurring 哨兵循环，ed71be88（*/30 心跳）功能冗余→pause 处置并披露（保留可恢复非删除）；本轮=ROUND=4；下一取号 s376。【六】合规：主会话 1 席+子智能体 0（配额 C=3 未用满；空转比 0）；节流合规；AOCI 零调用；回执镜像 outbox/c/ cc:A_MAIN；候回执=trae 二切片 ack+claude PROJ-FE-01 摘票 ack+V2 RT 复核+P2 iteration11+B 剩余三项裁定。", "status": "ACTIVE"}
'@
if ($line -match "`n") { throw "MULTILINE_GUARD_FAIL" }
if ($line -notmatch '^\{"id": "s375-') { throw "FORMAT_GUARD_FAIL" }

# 4. append（UTF-8 无 BOM）
[System.IO.File]::AppendAllText($mbPath, $line + "`n", (New-Object System.Text.UTF8Encoding($false)))

# 5. 复验
$after = [System.IO.File]::ReadAllLines($mbPath)
if ($after.Count -ne ($lines.Count + 1)) { throw "LINECOUNT_FAIL: $($after.Count) != $($lines.Count + 1)" }
if (-not $after[$after.Count-1].Contains('s375-gov-rt-evidence-v2ratify-esc-20261022')) { throw "TAIL_VERIFY_FAIL" }
Write-Output ("APPEND_OK lines={0} tail=s375" -f $after.Count)

# 6. 镜像件（raw 尾部 status 后插 cc:A_MAIN）
$img = $line.TrimEnd().TrimEnd('}')
$img = $img + ', "cc": "A_MAIN"}'
[System.IO.File]::WriteAllText($imgPath, $img, (New-Object System.Text.UTF8Encoding($false)))
$chk = Get-Content $imgPath -Raw
if ($chk -notmatch '"cc": "A_MAIN"\}') { throw "MIRROR_FAIL" }
Write-Output "MIRROR_OK outbox/c/c-report-rt-evidence-v2ratify-esc-20261022.json"
