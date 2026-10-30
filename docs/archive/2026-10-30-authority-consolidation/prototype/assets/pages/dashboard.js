/* ============================================================
   工作台 Dashboard + 全局搜索
   ============================================================ */
(function(){
App.reg('#/dashboard', '工作台', function(){
  var envName = {dev:'开发环境', staging:'联调环境', prod:'生产环境'}[DB.env] || DB.env;
  /* 统计 */
  var totalRows = DB.metaTables.reduce(function(s,t){return s+t.rows;},0);
  var wfOnline = DB.workflows.filter(function(w){return w.status==='online';}).length;
  var streamRun = DB.streamJobs.filter(function(s){return s.status==='running';}).length;
  var qcScore = DB.qcReports[0].score;

  var html = '<div class="welcome-banner" style="background:linear-gradient(120deg,#0e2a5c 0%,#1668dc 60%,#4d9aff 100%);border-radius:12px;padding:26px 30px;color:#fff;margin-bottom:18px">'
    +'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:14px">'
    +'<div><div style="font-size:20px;font-weight:700">下午好，'+DB.user.name+' 👋</div>'
    +'<div style="opacity:.85;font-size:12.5px;margin-top:6px">今天是 '+now+' · 当前环境 <b>'+envName+'</b> · 平台运行正常，昨晚 1 个工作流实例失败待处理、2 条待办审批等待您的操作</div></div>'
    +'<div style="display:flex;gap:10px">'
    +'<button class="btn" style="background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.35);color:#fff" onclick="App.go(\'#/qc/exception\')">核查质量异常</button>'
    +'<button class="btn" style="background:#fff;color:var(--primary);border:none;font-weight:600" onclick="App.go(\'#/dag/runs\')">处理失败实例</button>'
    +'</div></div></div>';

  /* 统计卡片 */
  html += '<div class="grid grid-4" style="margin-bottom:16px">'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/meta/catalog\')"><span class="type-icon" style="background:#1668dc">▤</span><div><div class="stat-num">'+DB.metaTables.length+'</div><div class="stat-label">数据表资产（共 '+fmt(totalRows)+' 行）</div></div></div>'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/ind/list\')"><span class="type-icon" style="background:#7c3aed">✦</span><div><div class="stat-num">'+DB.indicators.length+'</div><div class="stat-label">统一指标（评审中 '+(DB.indApprovals.filter(function(a){return a.status==='review';}).length)+'）</div></div></div>'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/qc/score\')"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+qcScore+'</div><div class="stat-label">质量评分（今日日报）</div></div></div>'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/dag/list\')"><span class="type-icon" style="background:#d97706">⑃</span><div><div class="stat-num">'+wfOnline+'</div><div class="stat-label">上线工作流（运行 '+(DB.wfInstances.filter(function(i){return i.status==='running';}).length)+'）</div></div></div>'
    +'</div>';
  html += '<div class="grid grid-4" style="margin-bottom:18px">'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/ds/list\')"><span class="type-icon" style="background:#0891b2">⛁</span><div><div class="stat-num">'+DB.datasources.length+'</div><div class="stat-label">数据源（异常 1）</div></div></div>'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/sync/list\')"><span class="type-icon" style="background:#c2410c">⇄</span><div><div class="stat-num">'+DB.syncBatches.length+'</div><div class="stat-label">同步批次（差异 1 / 运行中 1）</div></div></div>'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/stream/list\')"><span class="type-icon" style="background:#0d9488">≈</span><div><div class="stat-num">'+streamRun+'</div><div class="stat-label">流任务运行中</div></div></div>'
    +'<div class="stat-card hoverable" onclick="App.go(\'#/dep/monitor\')"><span class="type-icon" style="background:#475569">⛅</span><div><div class="stat-num">'+DB.components.filter(function(c){return c.status==='running';}).length+'/'+DB.components.length+'</div><div class="stat-label">集群组件健康</div></div></div>'
    +'</div>';

  /* 待办中心 */
  var todos = [
    {ico:'⛔', color:'var(--danger)', bg:'var(--danger-bg)', title:'工作流实例失败 R20260912-001（订单主题日增）', desc:'节点「支付日汇总」失败 3 次重试后终止，阻塞下游 2 节点', btn:'断点恢复', go:'#/dag/runs'},
    {ico:'⚑', color:'var(--warn)', bg:'var(--warn-bg)', title:'质量异常待核查 QE20260912-001', desc:'QC-R-012 支付金额范围检查：异常 12 行（负值/超上限）', btn:'去核查', go:'#/qc/exception'},
    {ico:'✦', color:'var(--purple)', bg:'#f1e9ff', title:'指标变更审批 IA20260911-01', desc:'支付转化率 v1→v2：访问口径 PV→UV', btn:'去审批', go:'#/ind/approval'},
    {ico:'⌇', color:'var(--primary)', bg:'var(--info-bg)', title:'标准审批 SA20260912-01', desc:'数据元 DE-004 支付渠道 v2 评审中', btn:'去评审', go:'#/std/approval'},
    {ico:'⇄', color:'var(--warn)', bg:'var(--warn-bg)', title:'同步差异待核 SYNC_20260911_001', desc:'ods_mysql_product_info 源目标差 2000 行', btn:'看板核对', go:'#/batch/board'}
  ];
  html += UI.card('待办中心 <span class="tag tag-red" style="vertical-align:2px">'+todos.length+'</span>',
    '<div class="grid" style="grid-template-columns:repeat(2,1fr)">'+todos.map(function(t,i){
      return '<div style="display:flex;gap:10px;align-items:center;padding:11px 13px;border:1px solid var(--border);border-radius:9px;background:#fff">'
        +'<div class="ci" style="background:'+t.bg+';color:'+t.color+';width:34px;height:34px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0">'+t.ico+'</div>'
        +'<div style="flex:1;min-width:0"><b style="font-size:12.8px">'+t.title+'</b><div style="color:var(--text-3);font-size:11.5px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+t.desc+'</div></div>'
        +'<button class="btn btn-sm" onclick="App.go(\''+t.go+'\')">'+t.btn+'</button></div>';
    }).join('')+'</div>');

  /* 图表区 */
  html += '<div class="grid" style="grid-template-columns:1.6fr 1fr;margin-top:18px;gap:16px">'
    + UI.card('质量评分趋势（近8日·分层）', Charts.line({labels:DB.qcScoreTrend.labels, series:[
        {name:'ODS', color:'#0891b2', data:DB.qcScoreTrend.ods},
        {name:'DWD', color:'#1668dc', data:DB.qcScoreTrend.dwd},
        {name:'DWS', color:'#7c3aed', data:DB.qcScoreTrend.dws},
        {name:'ADS', color:'#16a34a', data:DB.qcScoreTrend.ads}]}) )
    + UI.card('六维质量得分', Charts.hbars(DB.qcDimScore.map(function(d){return {name:d.name.slice(0,3), value:d.score, max:100, suffix:' 分', color:d.score>=95?'linear-gradient(90deg,#16a34a,#4ade80)':(d.score>=90?'linear-gradient(90deg,#1668dc,#4d9aff)':'linear-gradient(90deg,#d97706,#fbbf24)')};})) )
    +'</div>';

  /* 快捷入口 */
  var quicks = [
    {t:'数据开发IDE', d:'多源SQL开发', go:'#/ide', ico:'⌨', c:'#1668dc'},
    {t:'DAG工作流', d:'调度与依赖编排', go:'#/dag/list', ico:'⑃', c:'#d97706'},
    {t:'数仓建模', d:'分层建模/物理化', go:'#/model/list', ico:'▤', c:'#7c3aed'},
    {t:'元数据目录', d:'资产检索与血缘', go:'#/meta/catalog', ico:'☰', c:'#0891b2'},
    {t:'数据标准', d:'数据元/代码标准', go:'#/std/element', ico:'⌇', c:'#16a34a'},
    {t:'一键部署', d:'信创环境套件', go:'#/dep/center', ico:'⛅', c:'#475569'}
  ];
  html += '<div class="card" style="margin-top:18px"><div class="card-head"><h3>快捷入口</h3></div><div class="card-body"><div class="grid" style="grid-template-columns:repeat(6,1fr)">'
    + quicks.map(function(q){
      return '<div class="stat-card hoverable" onclick="App.go(\''+q.go+'\')"><span class="type-icon" style="background:'+q.c+'">'+q.ico+'</span><div><b style="font-size:12.5px">'+q.t+'</b><div style="font-size:11px;color:var(--text-3)">'+q.d+'</div></div></div>';
    }).join('')+'</div></div></div>';

  /* 今日运行概览 */
  html += '<div class="grid" style="grid-template-columns:1fr 1fr;gap:16px;margin-top:18px">'
    + UI.card('最近工作流实例',
      UI.tbl({id:'t_dash_wf', rowKey:'id', pageSize:4, searchKeys:['id','wfName'], data:function(){return DB.wfInstances;},
        cols:[{t:'实例', k:'id', render:function(r){return '<a onclick="App.go(\'#/dag/runs\')"><b>'+r.id+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.wfName+'</div>';}},
              {t:'业务日期', k:'bizDate'},
              {t:'状态', render:function(r){return st(r.status);}}],
        ops:function(r){return '<a onclick="App.go(\'#/dag/runs\')">详情</a>';}}))
    + UI.card('运行中流任务',
      UI.tbl({id:'t_dash_st', rowKey:'id', pageSize:4, searchKeys:['id','name'], data:function(){return DB.streamJobs;},
        cols:[{t:'任务', k:'name', render:function(r){return '<a onclick="App.go(\'#/stream/list\')"><b>'+UI.esc(r.name)+'</b></a>';}},
              {t:'TPS', render:function(r){return r.metrics.tps? '<b>'+fmt(r.metrics.tps)+'</b>' : '-';}},
              {t:'状态', render:function(r){return st(r.status);}}],
        ops:function(r){return '<a onclick="App.go(\'#/stream/list\')">监控</a>';}}))
    +'</div>';
  return html;
});

/* ---- 全局搜索结果页 ---- */
App.reg('#/search', '全局搜索', function(p, q){
  var kw = q? decodeURIComponent(q.replace('q=','')) : '';
  kw = UI.esc(kw);
  var hit = function(s){ return String(s||'').toLowerCase().indexOf(kw.toLowerCase())>=0; };
  var tables = DB.metaTables.filter(function(t){return hit(t.name)||hit(t.desc)||hit(t.domain);});
  var inds = DB.indicators.filter(function(i){return hit(i.name)||hit(i.en)||hit(i.id);});
  var dss = DB.datasources.filter(function(d){return hit(d.name)||hit(d.type)||hit(d.host);});
  var wfs = DB.workflows.filter(function(w){return hit(w.name)||hit(w.id);});
  var stds = DB.stdElements.filter(function(s){return hit(s.cn)||hit(s.en)||hit(s.id);});
  var total = tables.length+inds.length+dss.length+wfs.length+stds.length;
  var html = UI.pageHead('全局搜索', '关键词「<b style="color:var(--primary)">'+kw+'</b>」共命中 <b>'+total+'</b> 条结果（数据表 '+tables.length+' · 指标 '+inds.length+' · 工作流 '+wfs.length+' · 数据源 '+dss.length+' · 标准 '+stds.length+'）');
  function sec(title, rows, cols){
    if(!rows.length) return '';
    return '<div class="card" style="margin-bottom:16px"><div class="card-head"><h3>'+title+'<span class="tag tag-blue" style="margin-left:8px;vertical-align:2px">'+rows.length+'</span></h3></div><div class="card-body">'
      + UI.tbl({id:'t_s_'+title.length+rows[0].id, rowKey:'id', pageSize:5, searchKeys:[], data:function(){return rows;}, cols:cols, ops:null}) +'</div></div>';
  }
  html += sec('数据表', tables, [
    {t:'表名', k:'name', render:function(r){return '<a onclick="App.go(\'#/meta/catalog\')"><b>'+r.name+'</b></a><div style="font-size:11px;color:var(--text-3)">'+UI.esc(r.desc)+'</div>';}},
    {t:'分层', k:'layer'},{t:'主题域', k:'domain'},{t:'负责人', k:'owner'}]);
  html += sec('指标', inds, [
    {t:'指标', k:'name', render:function(r){return '<a onclick="App.go(\'#/ind/list\')"><b>'+r.name+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+UI.esc(r.bizDef)+'</div>';}},
    {t:'类型', k:'type'},{t:'来源表', k:'srcTable'},{t:'负责人', k:'owner'}]);
  html += sec('工作流', wfs, [
    {t:'工作流', k:'name', render:function(r){return '<a onclick="App.go(\'#/dag/list\')"><b>'+r.name+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+UI.esc(r.desc)+'</div>';}},
    {t:'周期', k:'cron'},{t:'负责人', k:'owner'},{t:'状态', render:function(r){return st(r.status);}}]);
  html += sec('数据源', dss, [
    {t:'数据源', k:'name', render:function(r){return '<a onclick="App.go(\'#/ds/detail/'+r.id+'\')"><b>'+UI.esc(r.name)+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+r.type+'</div>';}},
    {t:'主机', k:'host'},{t:'环境', k:'env'},{t:'状态', render:function(r){return st(r.status);}}]);
  html += sec('数据标准', stds, [
    {t:'数据元', k:'cn', render:function(r){return '<a onclick="App.go(\'#/std/element\')"><b>'+r.cn+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+r.en+'</div>';}},
    {t:'类型', k:'type'},{t:'主题域', k:'domain'},{t:'状态', render:function(r){return st(r.status);}}]);
  if(!total) html += '<div class="card no-head"><div class="card-body"><div class="empty"><span class="e-ico">⌕</span><p>未找到与「'+kw+'」相关的结果，可尝试：表名 / 指标名 / 任务名 / 数据源名</p><a onclick="location.hash=\'#/dashboard\'">返回工作台</a></div></div></div>';
  return html;
});
})();
