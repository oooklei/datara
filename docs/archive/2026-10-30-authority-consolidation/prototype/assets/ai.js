/* ============================================================
   Datara 智能助手（全局 AI 助手）
   - 右下角悬浮球 + 右侧抽屉对话
   - 场景化：按当前路由注入上下文与快捷动作（建表/稽核/归因/优化）
   - 各模块通过 AI.act(id) 触发场景动作（如 M04 的 AI 建表）
   ============================================================ */
var AI = (function(){
  var open = false;
  var msgBox, actsBox, ctxBox;

  /* 场景注册表：route前缀 -> {ctx, acts:[{id,label,reply}]} */
  var SCENES = [
    {p:'#/model', ctx:'数仓建模 · 命名规范 DWD_<域>_<过程>，分层 DWD/DWS/ADS/DIM', acts:[
      {id:'md_table', label:'✦ AI 建表助手', fn:'A.mdAiWizard'},
      {id:'md_audit', label:'稽核模型规范', reply:'模型规范稽核完成：\n① 3 个模型命名符合 DWD/DWS 前缀规范 ✓\n② 1 个模型（dwd_trade_pay）缺少业务过程后缀 → 建议改为 dwd_trade_pay_detail\n③ 所有事实表均已关联日期维度 ✓\n④ dws_trade_1d 缺少数据域标注 → 已给出推荐：交易域\n\n可点击「应用全部建议」一键整改，整改后进入人工核验。'},
      {id:'md_dim', label:'推荐关联维表', reply:'基于表字段分析（含 trade_no、user_id、shop_id、pay_type）：\n· user_id → 建议关联 dim_user（会员维）· 已存在 ✓\n· shop_id → 建议关联 dim_shop（门店维）· 已存在 ✓\n· pay_type → 未发现字典表 → 已按命名规范自动生成 dim_dict_pay_type（编码/名称/排序/是否启用）并关联 ✓\n\n维表外键稽核：代理键 _sk 命名规范，均已通过。'}]},
    {p:'#/std', ctx:'数据标准 · 稽核口径：命名规范/取值域/编码字典', acts:[
      {id:'std_audit', label:'AI 全量稽核', reply:'数据标准稽核报告（抽样 128 字段）：\n· 命名符合标准：119（93.0%）\n· 取值域冲突：4 项 —— gender 字段存在 M/F 与 1/2 两套编码，建议统一采用 STD_GEN_001（GB/T 2261.1）\n· 缺失标准：5 项 —— 手机号、证件号等未挂接数据元，已推荐对应标准\n\n生成整改清单 9 条（可一键下发工单 → 责任人整改 → 复核归档）。'},
      {id:'std_fix', label:'一键生成整改工单', reply:'已生成 9 张整改工单并派发：\n· 张三（交易域）：3 张 · 李四（用户域）：4 张 · 王五（财务域）：2 张\n预计 3 个工作日内完成，完成后自动触发复核任务。'}]},
    {p:'#/qc', ctx:'数据质量 · 六维评估：完整性/准确性/一致性/及时性/唯一性/有效性', acts:[
      {id:'qc_attr', label:'异常归因分析', reply:'当前 3 条异常归因分析：\n① ods_gdb_biz_user_info.user_id 非空违例 214 条 → 上游 SYNC_20260911_003 增量时间窗重叠导致重复写入（置信度 92%），建议改用 merge 幂等写入\n② dwd_order_pay_detail.pay_amt 越界 3 条 → 源系统促销活动负数冲销未过滤，建议增加有效性规则 amt>=0 OR bill_type=冲销\n③ dws_trade_1d 波动超阈值 → 昨日下游重跑，非数据问题，无需处理\n\n已将建议转为质量规则草稿，可在规则库确认发布。'},
      {id:'qc_rule', label:'推荐质量规则', reply:'基于表结构与业务语义，推荐 5 条规则：\n· 唯一性：order_no 全表唯一\n· 有效性：pay_date ∈ 业务日期范围\n· 完整性：user_id 非空率 ≥ 99.9%\n· 一致性：sum(pay_amt) 对账 dws 层偏差 ≤ 0.1%\n· 及时性：T-1 数据 06:00 前就绪\n一键采纳后将挂接到对应任务流节点。'}]},
    {p:'#/ide', ctx:'SQL 开发 IDE · 解析/格式化/测试/发布', acts:[
      {id:'ide_opt', label:'SQL 优化建议', reply:'对当前脚本扫描结果：\n① SELECT * → 建议显式列出 12 个所需字段，减少 IO 38%\n② WHERE 对 pay_date 使用函数 → 索引失效，改为区间过滤\n③ 3 表 JOIN 建议按 20:1 选择性调整驱动顺序，预计耗时 4.2s → 1.1s\n\n已生成优化版 SQL（可一键替换并保留原版注释备份）。'},
      {id:'ide_fmt', label:'AI 格式化+补注释', fn:'A.ideAiFmt'}]},
    {p:'#/sync', ctx:'数据同步 · 批/CDC · 幂等写入', acts:[
      {id:'sync_diag', label:'同步失败归因', reply:'最近 24h 同步失败 2 次：\n① SYNC_20260912_002：目标库连接池耗尽（峰值连接 198/200）→ 建议写入并发降为 8 或扩容连接池\n② SYNC_20260911_004：源端 Binlog 位点过期 → 已自动重置到最近 GTID 并断点续传\n\n同类问题防复：已推荐失败自动降并发策略，可在同步配置开启。'}]},
    {p:'#/dag', ctx:'工作流调度 · 依赖与 SLA', acts:[
      {id:'dag_retry', label:'失败任务处置建议', reply:'工作流失败节点处置建议：\n① dwd_trade_1d：重试 3 次均失败于内存溢出 → 建议 executor 内存 4G→8G，或拆分分区并行\n② 下游影响：ads_board_1d、ind_snapshot 共 2 个任务被阻塞 → 建议先补数再恢复，已在依赖图标红\n\n一键「自动重试+内存调优」已生成变更单，审批后生效。'}]},
    {p:'#/dep', ctx:'部署运维 · 信创环境健康度', acts:[
      {id:'dep_diag', label:'资源健康诊断', reply:'集群健康诊断：\n① node-03 磁盘使用率 87% → 建议 72h 内扩容或清理 30 天前日志（可自动执行）\n② node-01 CPU 峰值 91%（ETL 窗口）→ 建议错峰调度 2 个任务\n③ 其余 6 节点指标正常 ✓\n\n已生成容量优化建议单。'}]},
    {p:'#/', ctx:'数据治理工作台', acts:[
      {id:'g_report', label:'生成今日巡检报告', reply:'【Datara 治理巡检 · 今日】\n· 数据源：8 个在线，0 异常 ✓\n· 批处理：12 任务成功 / 1 重试成功 / 1 失败（已归因）\n· 质量：全库 92.4 分，3 条异常待处理\n· SLA：2 个工作流临近截止（84%）\n· 标准/指标：5 项待评审\n\n建议优先处理：同步失败归因 → 质量异常 → SLA 风险。'},
      {id:'g_help', label:'平台使用指引', reply:'平台主业务主线：\n① 接入：注册数据源 → 连通测试 → 抽取元数据\n② 建模：分层建模 → 物理化 → 版本管理\n③ 开发：SQL IDE / ETL 设计器 → 发布为工作流 DAG\n④ 运维：调度实例 → SLA 告警 → 失败重试\n⑤ 治理：质量检核 → 标准稽核 → 血缘影响分析\n\n任一页面右侧 ? 图标可查看该页操作指引。'}]}
  ];

  function scene(){
    var h = location.hash || '#/dashboard';
    for(var i=0;i<SCENES.length;i++){
      if(h.indexOf(SCENES[i].p)===0){
        if(SCENES[i].p==='#/' && h.length>2) continue;
        return SCENES[i];
      }
    }
    return SCENES[SCENES.length-1];
  }

  function mount(){
    if(document.getElementById('aiDrawer')) return;
    var d = document.createElement('div');
    d.innerHTML =
      '<button class="ai-fab" onclick="AI.toggle()" title="Datara 智能助手"><span class="ai-pulse"></span>✦</button>'
      + '<div class="ai-drawer" id="aiDrawer">'
      + '<div class="ai-head"><span class="ai-logo">✦</span><div><b>Datara 智能助手</b><div class="ai-sub">大模型驱动 · 稽核 / 归因 / 生成 / 优化</div></div><span class="ai-x" onclick="AI.toggle()">✕</span></div>'
      + '<div class="ai-ctx" id="aiCtx"></div>'
      + '<div class="ai-msgs" id="aiMsgs"></div>'
      + '<div class="ai-acts" id="aiActs"></div>'
      + '<div class="ai-input"><input id="aiIn" placeholder="输入问题，回车发送…" onkeydown="if(event.key===\'Enter\')AI.send()"><button onclick="AI.send()">发送</button></div>'
      + '</div>';
    document.body.appendChild(d);
    msgBox = document.getElementById('aiMsgs');
    actsBox = document.getElementById('aiActs');
    ctxBox = document.getElementById('aiCtx');
    bot('您好，我是 Datara 智能助手 ✦\n可对建模/标准/质量/SQL/调度做「稽核、归因、生成、优化」，试试下方快捷动作。');
    refreshScene();
  }

  function refreshScene(){
    if(!ctxBox) return;
    var s = scene();
    ctxBox.innerHTML = '<b>当前场景</b>：'+UI.esc(s.ctx);
    actsBox.innerHTML = s.acts.map(function(a){ return '<span class="ai-act" onclick="AI.act(\''+a.id+'\')">'+a.label+'</span>'; }).join('');
  }

  function push(cls, html){
    var m = document.createElement('div');
    m.className = 'ai-msg '+cls; m.innerHTML = html;
    msgBox.appendChild(m); msgBox.scrollTop = msgBox.scrollHeight;
    return m;
  }
  function bot(text){ push('bot', UI.esc(text).replace(/\n/g,'<br>')); }
  function typing(){
    var t = push('bot', '<span class="ai-typing"><i></i><i></i><i></i> 思考中…</span>');
    return t;
  }

  function answer(q){
    var s = scene();
    var qs = q.toLowerCase();
    if(qs.indexOf('怎么')>=0||qs.indexOf('如何')>=0||qs.indexOf('指引')>=0||qs.indexOf('流程')>=0)
      return s.acts[s.acts.length-1].reply || '请使用快捷动作，或描述具体问题。';
    return '已收到您的问题：「'+q+'」。\n\n基于当前场景（'+s.ctx+'）的分析结论：\n· 已定位相关对象并完成健康度扫描\n· 生成建议 3 条，可通过快捷动作一键应用\n\n如需更精确的结果，请点击上方与场景匹配的快捷动作。';
  }

  return {
    toggle: function(){
      open = !open;
      document.getElementById('aiDrawer').classList.toggle('open', open);
      if(open) refreshScene();
    },
    open: function(){ if(!open) AI.toggle(); },
    close: function(){ if(open) AI.toggle(); },
    send: function(){
      var inp = document.getElementById('aiIn');
      var q = inp.value.trim(); if(!q) return;
      inp.value = '';
      push('user', UI.esc(q));
      var t = typing();
      setTimeout(function(){ t.remove(); bot(answer(q)); }, 700);
    },
    act: function(id){
      var s = scene();
      var a = s.acts.find(function(x){return x.id===id;}); if(!a) return;
      push('user', a.label.replace(/^✦\s*/,''));
      if(a.fn && window[a.fn.split('.')[0]]){
        /* 场景动作委托给模块实现（如 A.mdAiWizard） */
        var parts = a.fn.split('.');
        try{ window[parts[0]][parts[1]](); }catch(e){ console.error(e); }
        return;
      }
      var t = typing();
      setTimeout(function(){ t.remove(); bot(a.reply || '动作已执行。'); }, 800);
    },
    mount: mount,
    refreshScene: refreshScene,
    /* 供模块打开助手并直接展示结果（如 M04 AI 建表、M10 AI 稽核） */
    show: function(text){
      AI.open(); refreshScene();
      var t = typing();
      setTimeout(function(){ t.remove(); bot(text); }, 500);
    }
  };
})();
document.addEventListener('DOMContentLoaded', function(){ AI.mount(); });
