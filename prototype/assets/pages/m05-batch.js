/* ============================================================
   M05 批处理与同步（P0：ETL设计器/SQL任务/批量同步向导/自动建表分区/数据量核对/看板/报告）
   ============================================================ */
(function(){
var syncStatus = {running:'running', success:'success', diff:'diff', failed:'failed'};

/* ---------- 同步任务列表 ---------- */
App.reg('#/sync/list', '同步任务', function(){
  var html = UI.pageHead('批量数据同步',
    '批量选表 → 自动建表+自动分区 → 自动同步 → 数据量核对；支持全量/增量/CDC，含同步数据量日志与核对报告',
    '<button class="btn btn-primary" onclick="App.go(\'#/sync/wizard\')">+ 批量同步向导</button>'
    +'<button class="btn" onclick="A.singleSync()">+ 单表同步</button>'
    +'<button class="btn" onclick="App.go(\'#/batch/board\')">进度看板</button>',
    '操作指引：① 「批量同步向导」五步完成：选数据源 → 选表（自动建表+分区） → 同步配置 → 调度配置 → 确认执行；② 批次运行中可终止，结束后可重跑与数据量核对；③ 核对差异将生成核对报告并可下载。批次状态流转见下方状态图。');
  html += UI.stateFlow([
    {k:'create', t:'批次创建',  d:'选表 · 自动建表分区'},
    {k:'run',    t:'同步执行',  d:'全量/增量/CDC · 分片并发'},
    {k:'check',  t:'数据量核对', d:'行数/校验值比对'},
    {k:'result', t:'核对完成',  d:'成功 / 差异 / 失败 → 报告'}
  ], null, '闭环说明：创建 → 执行 → 核对 → 报告归档；存在差异可一键重跑差异表，失败表自动重试（可配置次数）后仍失败则告警。');
  html += UI.card('同步批次列表', UI.tbl({
    id:'t_sync', rowKey:'id', pageSize:8, searchKeys:['id','srcName','target','mode'], searchPh:'搜索批次/数据源',
    filters:[{k:'status', label:'状态', options:[{v:'running',t:'运行中'},{v:'success',t:'成功'},{v:'diff',t:'存在差异'},{v:'failed',t:'失败'}]}],
    data:function(){ return DB.syncBatches; },
    cols:[
      {t:'批次ID', k:'id', sortable:true, render:function(r){ return '<a onclick="App.go(\'#/sync/detail/'+r.id+'\')" class="mono"><b>'+r.id+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.startAt+' 起</div>'; }},
      {t:'链路', render:function(r){ return UI.esc(r.srcName)+' → '+UI.esc(r.target)+'<div style="font-size:11px;color:var(--text-3)">'+r.mode+' · '+r.strategy+'</div>'; }},
      {t:'调度', render:function(r){ return '<span class="mono">'+r.cron+'</span><div style="font-size:11px;color:var(--text-3)">并发 '+r.concurrency+' · 失败重试 '+r.retry+' 次</div>'; }},
      {t:'表进度', render:function(r){
        var done = r.ok + r.diff + r.fail;
        var pct = Math.round(done/r.total*100);
        return '<div style="min-width:130px"><div class="progress '+(r.status==='failed'?'red':(r.status==='diff'?'orange':''))+'"><div class="bar" style="width:'+pct+'%"></div></div><div style="font-size:11px;color:var(--text-3);margin-top:3px">'+done+'/'+r.total+' · 成功'+r.ok+' 差异'+r.diff+' 失败'+r.fail+'</div></div>';
      }},
      {t:'数据量核对', render:function(r){
        var dc = r.srcRows - r.tgtRows;
        return '<span class="mono" style="color:'+(dc===0?'var(--success)':'var(--danger)')+'">'+fmt(r.tgtRows)+' / '+fmt(r.srcRows)+'</span><div style="font-size:11px;color:var(--text-3)">差异 '+fmt(dc)+' 行</div>';
      }},
      {t:'状态', k:'status', render:function(r){ return st(r.status); }}
    ],
    ops:function(r){
      return '<a onclick="App.go(\'#/sync/detail/'+r.id+'\')">详情</a>'
        + (r.status==='running' ? '<a onclick="A.syncKill(\''+r.id+'\')">终止</a>'
          : '<a onclick="A.syncRerun(\''+r.id+'\')">重跑</a><a onclick="A.syncCheck(\''+r.id+'\')">数据核对</a>')
        + '<a class="danger" onclick="A.syncDel(\''+r.id+'\')">删除</a>';
    }
  }));
  return html;
});

/* 同步详情 */
App.reg('#/sync/detail/:id', '同步批次详情', function(p){
  var b = DB.syncBatches.find(function(x){return x.id===p.id;});
  if(!b) return '<div class="empty">批次不存在</div>';
  var html = UI.pageHead('<a onclick="App.go(\'#/sync/list\')">← 同步任务</a> / '+b.id,
    UI.esc(b.srcName)+' → '+UI.esc(b.target)+' · '+b.mode+' · '+b.strategy+' · '+b.startAt+' ~ '+b.endAt,
    (b.status!=='running'?'<button class="btn" onclick="A.syncRerun(\''+b.id+'\')">重跑批次</button><button class="btn" onclick="A.syncCheck(\''+b.id+'\')">数据量核对</button><button class="btn btn-primary" onclick="A.syncReport(\''+b.id+'\')">⇩ 核对报告</button>':'<button class="btn" onclick="A.syncKill(\''+b.id+'\')">终止批次</button>')
    + st(b.status));
  html += '<div class="grid grid-4">'
    +'<div class="stat-card"><div><div class="stat-num">'+b.total+'</div><div class="stat-label">总表数</div></div></div>'
    +'<div class="stat-card"><div><div class="stat-num" style="color:var(--success)">'+b.ok+'</div><div class="stat-label">成功</div></div></div>'
    +'<div class="stat-card"><div><div class="stat-num" style="color:var(--warn)">'+b.diff+'</div><div class="stat-label">数据差异</div></div></div>'
    +'<div class="stat-card"><div><div class="stat-num" style="color:var(--danger)">'+b.fail+'</div><div class="stat-label">失败</div></div></div></div>';
  html += UI.card('同步数据量日志与核对明细（源表 COUNT(*) vs 入仓 COUNT(*)）', UI.tbl({
    id:'t_synclog', rowKey:'st', pageSize:10, searchKeys:['st','tt'],
    data:function(){ return b.logs; },
    cols:[
      {t:'源表', k:'st', render:function(r){ return '<span class="mono">'+r.st+'</span>'; }},
      {t:'目标表', k:'tt', render:function(r){ return '<span class="mono">'+r.tt+'</span>'; }},
      {t:'源端数据量', render:function(r){ return '<span class="mono">'+fmt(r.sc)+'</span>'; }},
      {t:'入仓数据量', render:function(r){ return '<span class="mono">'+fmt(r.tc)+'</span>'; }},
      {t:'差异', render:function(r){ var d=r.sc-r.tc; return '<span class="mono" style="color:'+(d===0?'var(--success)':'var(--danger)')+';font-weight:600">'+fmt(d)+'</span>'; }},
      {t:'分区', render:function(r){ return '<span class="mono">dt='+(b.startAt.slice(0,10))+'</span>'; }},
      {t:'耗时', k:'dur'},
      {t:'状态', k:'status', render:function(r){ return st(r.status); }}
    ],
    ops:function(r){
      if(r.status==='diff') return '<a onclick="A.diffDetail(\''+r.st+'\')">差异详情</a><a onclick="A.resync(\''+b.id+'\',\''+r.st+'\')">重新同步</a><a onclick="A.manualFix(\''+r.st+'\')">手动修复</a>';
      if(r.status==='failed') return '<a onclick="A.errDetail(\''+r.st+'\')">错误详情</a><a onclick="A.resync(\''+b.id+'\',\''+r.st+'\')">重新同步</a>';
      return '<a onclick="UI.toast(\'查看入仓抽样：SELECT * FROM '+r.tt+' LIMIT 10\',\'info\')">抽样查看</a>';
    }
  }));
  html += UI.card('DDL预览（自动建表 · 自动分区）', '<div class="code-box"><span class="kw">CREATE TABLE</span> ods_mysql_product_info (\n  product_id  <span class="kw">BIGINT</span>,\n  product_name <span class="kw">VARCHAR</span>(200),\n  price       <span class="kw">DECIMAL</span>(12,2),\n  create_time <span class="kw">DATETIME</span>\n)\n<span class="kw">PARTITION BY</span> (dt)              <span class="cm">-- 按天自动分区</span>\n<span class="kw">DISTRIBUTED BY</span> <span class="kw">HASH</span>(product_id) <span class="kw">BUCKETS</span> 10\n<span class="kw">PROPERTIES</span>(<span class="str">"replication_num"</span>=<span class="str">"3"</span>);</div>'
    + '<div style="margin-top:10px;display:flex;gap:8px"><button class="btn" onclick="UI.download(\'ods_mysql_product_info.sql\', document.querySelector(\'.code-box\').innerText)">⇩ 下载DDL</button><button class="btn" onclick="UI.toast(\'已打开字段类型映射规则：MySQL BIGINT→Doris BIGINT / VARCHAR→VARCHAR / DATETIME→DATETIME\',\'info\')">字段类型映射规则</button></div>');
  return html;
});
A.syncKill = function(id){
  UI.confirm({title:'终止批次', danger:true, msg:'确认终止批次「'+id+'」？', detail:'未完成的表将标记为失败，可重跑续传。', onOk:function(){
    var b = DB.syncBatches.find(function(x){return x.id===id;}); b.status='failed';
    b.logs.forEach(function(l){ if(l.status==='waiting'||l.status==='running') l.status='failed'; });
    UI.toast('批次已终止', 'success'); App.resolve();
  }});
};
A.syncRerun = function(id){
  UI.confirm({title:'重跑批次', msg:'确认重跑批次「'+id+'」？', detail:'仅重跑失败与差异表，成功表自动跳过（断点续跑）。', onOk:function(){
    var b = DB.syncBatches.find(function(x){return x.id===id;});
    b.logs.forEach(function(l){ if(l.status==='failed'||l.status==='diff'){ l.status='success'; l.tc=l.sc; l.dc=0; l.dur=(10+Math.floor(Math.random()*40))+'s'; } });
    b.ok = b.logs.filter(function(l){return l.status==='success';}).length;
    b.diff = 0; b.fail = 0; b.status='success';
    b.tgtRows = b.srcRows;
    UI.toast('断点续跑完成：失败/差异表已全部重新同步成功', 'success'); App.resolve();
  }});
};
A.syncCheck = function(id){
  var b = DB.syncBatches.find(function(x){return x.id===id;});
  UI.toast('正在执行数据量核对：逐表 COUNT 比对 ...', 'info');
  setTimeout(function(){
    var d = b.srcRows - b.tgtRows;
    UI.modal({title:'数据量核对结果 - '+b.id, footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="UI.closeModal();A.syncReport(\''+b.id+'\')">生成核对报告</button>', body:
      '<div class="checker-line '+(d===0?'ok':'err')+'"><span>'+(d===0?'✓':'✗')+'</span><b>'+(d===0?'全表数据量一致':'存在差异 '+fmt(d)+' 行')+'</b><span style="margin-left:auto">'+fmt(b.tgtRows)+' / '+fmt(b.srcRows)+'</span></div>'
      +'<div class="checker-line ok"><span>✓</span><b>分区校验</b><span style="margin-left:auto">dt='+b.startAt.slice(0,10)+' 分区存在且有数据</span></div>'
      +'<div class="checker-line ok"><span>✓</span><b>空表校验</b><span style="margin-left:auto">无空表</span></div>'});
  }, 900);
};
A.syncReport = function(id){
  var b = DB.syncBatches.find(function(x){return x.id===id;});
  var lines = ['同步核对报告', '批次:'+b.id, '链路:'+b.srcName+' -> '+b.target, '时间:'+b.startAt+' ~ '+b.endAt, '', '源表,目标表,源行数,入仓行数,差异,状态,耗时'];
  b.logs.forEach(function(l){ lines.push([l.st,l.tt,l.sc,l.tc,(l.sc-l.tc),l.status,l.dur].join(',')); });
  lines.push('', '汇总: 总表数 '+b.total+' / 成功 '+b.ok+' / 差异 '+b.diff+' / 失败 '+b.fail);
  UI.download(b.id+'_核对报告.csv', lines.join('\n'), 'text/csv;charset=utf-8');
};
A.diffDetail = function(tbl){
  UI.modal({title:'差异详情 - '+tbl, w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="UI.closeModal();UI.toast(\'差异表已重新同步，差异 0 行\',\'success\');App.resolve()">重新同步该表</button>', body:
    '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>源端 80,000 行 vs 入仓 78,000 行，差异 2,000 行；疑似源端在同步窗口内发生写入（增量未覆盖）。</span></div>'
    + UI.tbl({id:'t_diff', rowKey:'id', pageSize:5, searchKeys:['pk'],
      data:function(){ return [{id:80001,pk:'P00001',reason:'同步窗口内新增'},{id:80002,pk:'P00002',reason:'同步窗口内新增'},{id:81234,pk:'P01234',reason:'主键冲突跳过'},{id:81235,pk:'P01235',reason:'主键冲突跳过'}]; },
      cols:[{t:'主键',k:'pk',render:function(r){return '<span class="mono">'+r.pk+'</span>';}},{t:'缺失原因',k:'reason'}], ops:null})});
};
A.errDetail = function(tbl){
  UI.modal({title:'错误详情 - '+tbl, footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    '<div class="code-box" style="color:#f87171">[ERROR] SyncTask-'+tbl+' 执行失败\njava.sql.SQLException: Access denied for user \'test_ro\'@\'%\' to database \'biz_test\'.user_address\n\n[排查建议]\n1. 检查账号对 user_address 表的 SELECT 权限\n2. 数据源连接诊断 → 权限验证\n3. 修复后使用「重新同步」断点续跑</div>'});
};
A.resync = function(bid, tbl){
  UI.toast('正在断点续跑 '+tbl+' ...', 'info');
  setTimeout(function(){
    var b = DB.syncBatches.find(function(x){return x.id===bid;});
    var l = b.logs.find(function(x){return x.st===tbl;});
    l.status='success'; l.tc=l.sc||1200; l.dc=0; l.dur='12s';
    b.ok = b.logs.filter(function(x){return x.status==='success';}).length;
    b.fail = b.logs.filter(function(x){return x.status==='failed';}).length;
    b.diff = b.logs.filter(function(x){return x.status==='diff';}).length;
    if(b.fail===0 && b.diff===0){ b.status='success'; b.tgtRows=b.srcRows; }
    UI.toast(tbl+' 同步成功', 'success'); App.resolve();
  }, 900);
};
A.manualFix = function(tbl){ UI.toast('已标记 '+tbl+' 为「已手动处理」，并记录操作审计', 'success'); };

/* 单表同步 */
A.singleSync = function(){
  UI.drawer({ title:'单表同步配置', w:'w-lg', body:
    '<div class="form-grid">'
    + UI.fSelect('源数据源', 'ss_ds', DB.datasources.map(function(d){return {v:d.id,t:d.name};}), {})
    + UI.fInput('源表名', 'ss_tbl', {ph:'如 user_info', req:true})
    + UI.fInput('目标表名', 'ss_tgt', {value:'ods_源库名_源表名'})
    + UI.fSelect('目标引擎', 'ss_engine', ['Apache Doris','Hive/Spark SQL','达梦 DM8','人大金仓 Kingbase','GaussDB DWS','万里 GreatDB'])
    + UI.fSelect('建表策略', 'ss_build', [{v:'auto',t:'自动建表（推荐）'},{v:'exists',t:'仅同步不建表'},{v:'rebuild',t:'建表并覆盖（危险）'}])
    + UI.fSelect('分区策略', 'ss_part', [{v:'day',t:'按天分区（推荐）'},{v:'month',t:'按月分区'},{v:'none',t:'不分区'},{v:'field',t:'按字段分区'}])
    + UI.fSelect('同步模式', 'ss_mode', [{v:'full',t:'全量同步'},{v:'inc',t:'增量同步（时间戳/CDC）'},{v:'first',t:'首次全量+后续增量（推荐）'}])
    + UI.fSelect('调度方式', 'ss_cron', [{v:'',t:'手动执行'},{v:'0 0 2 * * ?',t:'每日 02:00'},{v:'0 0 * * * ?',t:'每小时'}])
    + '</div>',
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.singleSyncSave()">保存任务</button>'});
};
A.singleSyncSave = function(){
  if(!UI.val('ss_tbl')){ UI.toast('请填写源表名', 'warn'); return false; }
  UI.toast('单表同步任务已创建：'+UI.val('ss_tbl')+' → '+UI.val('ss_tgt')+'（自动建表+按天分区）', 'success');
};

/* ---------- 批量同步向导（5步） ---------- */
App.reg('#/sync/wizard', '批量同步向导', function(){
  return UI.pageHead('批量同步向导', '五步完成批量同步：选择数据源 → 选择表 → 同步配置 → 调度配置 → 确认执行')
    + '<div class="card no-head"><div class="card-body" id="wizBody"></div></div>';
});
var W = {step:0, src:null, tables:[], picked:{}, cfg:{build:'auto', part:'day', mode:'first', prefix:'ods_', concurrency:5, cron:'0 0 2 * * ?', retry:2, intoDag:true}};
App.onAfterRender(function(){ A.wzRender(); });
A.wzRender = function(){
  if(!document.getElementById('wizBody')) return; /* 跨页残留钩子保护 */
  var s = W.step, steps=['选择数据源','选择表','同步配置','调度配置','确认执行'], inner='';
  if(s===0){
    inner = UI.tbl({id:'t_wzds', rowKey:'id', pageSize:8, searchKeys:['name','type'],
      data:function(){ return DB.datasources.filter(function(d){return d.type!=='Kafka';}); },
      cols:[{t:'数据源',render:function(r){return '<b>'+UI.esc(r.name)+'</b> <div style="font-size:11px;color:var(--text-3)">'+r.type+' · '+UI.esc(r.host)+'</div>';}},{t:'环境',k:'env',render:function(r){return tag(r.env, r.env==='生产'?'red':'orange');}},{t:'健康',render:function(r){return '<span class="st '+(r.health==='健康'?'st-green':'st-orange')+'"><i class="dot"></i>'+r.health+'</span>';}}],
      ops:function(r){ return '<a onclick="A.wzPickDs(\''+r.id+'\')">选择该数据源 →</a>'; }});
  }
  if(s===1){
    var all = W.tables.length? W.tables : [
      {n:'user_info', rows:1250000, size:'320MB', cols:8, up:'2026-09-11 23:59'},
      {n:'order_info', rows:5000000, size:'1.2GB', cols:12, up:'2026-09-11 23:58'},
      {n:'product_info', rows:80000, size:'95MB', cols:7, up:'2026-09-11 20:11'},
      {n:'user_address', rows:340000, size:'60MB', cols:9, up:'2026-09-11 23:50'},
      {n:'pay_log', rows:3200000, size:'780MB', cols:10, up:'2026-09-11 23:59'},
      {n:'member_level', rows:120000, size:'25MB', cols:6, up:'2026-09-11 12:00'},
      {n:'coupon_record', rows:890000, size:'180MB', cols:11, up:'2026-09-11 23:59'}
    ];
    W.tables = all;
    inner = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>已自动扫描数据源【'+(DB.datasources.find(function(d){return d.id===W.src;})||{}).name+'】，共 25 张表（演示展示 7 张），支持搜索/筛选/全选。</span></div>'
      + UI.tbl({id:'t_wztbl', rowKey:'n', pageSize:10, searchKeys:['n'], selectable:true,
        toolbarActs:function(){ return '<span style="font-size:12.5px;color:var(--text-2)">已选 <b id="wzCnt">'+Object.keys(W.picked).length+'</b> 张表</span><button class="btn btn-sm" onclick="A.wzSelAll()">全选</button>'; },
        data:function(){ return all; },
        cols:[{t:'表名',k:'n',render:function(r){return '<span class="mono">'+r.n+'</span>';}},{t:'行数',render:function(r){return '<span class="mono">'+fmt(r.rows)+'</span>';}},{t:'大小',k:'size'},{t:'字段数',k:'cols'},{t:'最后更新',k:'up'}],
        ops:function(r){ return '<a onclick="A.wzPreview(\''+r.n+'\')">预览结构</a>'; }})
      + '<div style="display:flex;justify-content:space-between"><button class="btn" onclick="A.wzStep(0)">← 上一步</button><button class="btn btn-primary" onclick="A.wzNext()">下一步 →</button></div>';
    // 恢复勾选
    setTimeout(function(){
      document.querySelectorAll('#tblw_t_wztbl .row-check').forEach(function(cb){
        var tr = cb.closest('tr'); var name = tr? tr.querySelector('.mono').innerText : null;
        if(name && W.picked[name]) cb.checked = true;
      });
      document.querySelectorAll('#tblw_t_wztbl .row-check').forEach(function(cb){
        cb.addEventListener('change', function(){
          var name = cb.closest('tr').querySelector('.mono').innerText;
          if(cb.checked) W.picked[name]=1; else delete W.picked[name];
          var c = document.getElementById('wzCnt'); if(c) c.innerText = Object.keys(W.picked).length;
        });
      });
    }, 30);
  }
  if(s===2){
    inner = '<div class="form-grid">'
      + UI.fSelect('目标库', 'c_target', ['Doris-分析集群','GaussDB-汇聚数仓','万里GreatDB-开发环境库'], {value:'Doris-分析集群'})
      + UI.fSelect('建表策略', 'c_build', [{v:'auto',t:'自动建表（推荐）·根据源表结构生成DDL'},{v:'exists',t:'仅同步不建表（表已存在）'},{v:'rebuild',t:'建表并覆盖（危险·删表重建）'}], {value:W.cfg.build})
      + UI.fSelect('分区策略', 'c_part', [{v:'day',t:'按天分区（推荐）dt=2026-09-11'},{v:'month',t:'按月分区'},{v:'none',t:'不分区'},{v:'field',t:'按字段分区'}], {value:W.cfg.part})
      + UI.fSelect('同步模式', 'c_mode', [{v:'full',t:'全量同步（每次覆盖）'},{v:'inc',t:'增量同步（时间戳/CDC）'},{v:'first',t:'首次全量+后续增量（推荐）'}], {value:W.cfg.mode})
      + UI.fInput('目标表名前缀', 'c_prefix', {value:W.cfg.prefix, help:'命名规则：ods_源库名_源表名（对齐命名规范 NR-01）'})
      + UI.fSelect('并发数', 'c_conc', [3,5,8,10].map(function(n){return {v:n,t:n+' 张并行'};}), {value:W.cfg.concurrency})
      + '</div><button class="btn" onclick="UI.toast(\'字段类型映射：MySQL BIGINT→Doris BIGINT / DATETIME→DATETIME / DECIMAL→DECIMAL(18,2)，已按规则自动映射\',\'info\')">查看字段类型映射</button>'
      + '<div style="display:flex;justify-content:space-between;margin-top:12px"><button class="btn" onclick="A.wzStep(1)">← 上一步</button><button class="btn btn-primary" onclick="A.wzNext()">下一步 →</button></div>';
  }
  if(s===3){
    inner = '<div class="form-grid">'
      + UI.fSelect('调度方式', 'd_cron', [{v:'',t:'手动执行'},{v:'0 0 2 * * ?',t:'每日 02:00（推荐）'},{v:'0 0 1 * * ?',t:'每日 01:00'},{v:'0 0 * * * ?',t:'每小时'}], {value:W.cfg.cron})
      + UI.fSelect('失败重试', 'd_retry', [1,2,3,5].map(function(n){return {v:n,t:'自动重试 '+n+' 次'};}), {value:W.cfg.retry})
      + '</div>'
      + '<div class="form-item"><div class="switch-row"><span class="switch on" id="d_dag" onclick="this.classList.toggle(\'on\')"></span><span style="font-size:12.5px">加入 DAG 工作流（生成「批量同步」工作流，支撑下游任务依赖）</span></div></div>'
      + '<div style="display:flex;justify-content:space-between;margin-top:8px"><button class="btn" onclick="A.wzStep(2)">← 上一步</button><button class="btn btn-primary" onclick="A.wzNext()">下一步 →</button></div>';
  }
  if(s===4){
    var n = Object.keys(W.picked).length || 7;
    inner = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>配置摘要确认，目标表将按规则自动命名，DDL 可预览修改。</span></div>'
      + UI.desc([['源数据源', (DB.datasources.find(function(d){return d.id===W.src;})||{}).name||'-'],
        ['同步表数量', n+' 张'],
        ['目标库', UI.val('c_target')||'Doris-分析集群'],
        ['建表策略', {auto:'自动建表',exists:'仅同步不建表',rebuild:'建表并覆盖（危险）'}[UI.val('c_build')||'auto']],
        ['分区策略', {day:'按天分区',month:'按月分区',none:'不分区',field:'按字段分区'}[UI.val('c_part')||'day']],
        ['同步模式', {full:'全量同步',inc:'增量同步',first:'首次全量+后续增量'}[UI.val('c_mode')||'first']],
        ['调度', UI.val('d_cron')||'手动执行'], ['失败重试', (UI.val('d_retry')||2)+' 次'],
        ['加入DAG', '是（生成批量同步工作流）']])
      + '<div class="card-head" style="border-bottom:none;padding:14px 0 6px"><h3>DDL预览（可编辑）</h3></div>'
      + '<div class="code-box" contenteditable="true">CREATE TABLE ods_mysql_user_info (\n  id BIGINT, user_name VARCHAR(100), phone VARCHAR(20),\n  create_time DATETIME, status INT\n)\nPARTITION BY (dt)\nDISTRIBUTED BY HASH(id) BUCKETS 10\nPROPERTIES("replication_num"="3");</div>'
      + '<div style="display:flex;justify-content:space-between;margin-top:12px"><button class="btn" onclick="A.wzStep(3)">← 上一步</button><button class="btn btn-primary" onclick="A.wzFinish()">▶ 开始同步</button></div>';
  }
  document.getElementById('wizBody').innerHTML = UI.steps(steps, s) + inner;
};
A.wzPickDs = function(id){ W.src = id; A.wzStep(1); };
A.wzStep = function(s){ W.step = s; App.go('#/sync/wizard'); setTimeout(A.wzRender, 0); };
A.wzNext = function(){
  var s = W.step;
  if(s===1){ if(!Object.keys(W.picked).length){ UI.toast('请至少勾选一张要同步的表', 'warn'); return; } A.wzStep(2); }
  else A.wzStep(s+1);
};
A.wzSelAll = function(){ W.tables.forEach(function(t){ W.picked[t.n]=1; }); document.querySelectorAll('#tblw_t_wztbl .row-check').forEach(function(cb){ cb.checked=true; }); var c=document.getElementById('wzCnt'); if(c) c.innerText = Object.keys(W.picked).length; };
A.wzPreview = function(n){
  UI.modal({title:'表结构预览 - '+n, w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.tbl({id:'t_wzpv', rowKey:'c0', pageSize:10, searchKeys:['c0'],
      data:function(){ return [['id','BIGINT','主键'],['user_name','VARCHAR(100)','姓名'],['phone','VARCHAR(20)','手机号'],['gender','CHAR(1)','性别'],['create_time','DATETIME','创建时间'],['update_time','DATETIME','更新时间'],['status','TINYINT','状态'],['amount','DECIMAL(18,2)','金额'],['dt','DATE','分区']].map(function(f){return {c0:f[0],c1:f[1],c2:f[2],c3:'自动映射 → '+f[1]};}); },
      cols:[{t:'字段',k:'c0',render:function(r){return '<span class="mono">'+r.c0+'</span>';}},{t:'源类型',k:'c1'},{t:'注释',k:'c2'},{t:'目标类型映射',k:'c3'}], ops:null})});
};
A.wzFinish = function(){
  var n = Object.keys(W.picked).length || 7;
  var bid = 'SYNC_20260912_002';
  DB.syncBatches.unshift({id:bid, srcDs:W.src, srcName:(DB.datasources.find(function(d){return d.id===W.src;})||{}).name||'数据源', target:UI.val('c_target')||'Doris-分析集群',
    mode:{full:'全量同步',inc:'增量同步',first:'首次全量+后续增量'}[UI.val('c_mode')||'first'],
    strategy:(UI.val('c_build')==='exists'?'仅同步不建表':'自动建表')+'+'+({day:'按天分区',month:'按月分区',none:'不分区',field:'按字段分区'}[UI.val('c_part')||'day']),
    total:n, ok:0, diff:0, fail:0, srcRows:0, tgtRows:0, status:'running', startAt:'2026-09-12 22:40:00', endAt:'-',
    cron:UI.val('d_cron')||'手动', concurrency:+(UI.val('c_conc')||5), retry:+(UI.val('d_retry')||2),
    logs:Object.keys(W.picked).slice(0,3).map(function(t){ return {st:t, tt:'ods_mysql_'+t, sc:100000, tc:0, dc:0, status:'waiting', dur:'-'}; })});
  UI.toast('批量同步批次「'+bid+'」已启动：'+n+' 张表，并发 '+(UI.val('c_conc')||5), 'success');
  App.go('#/batch/board');
};

/* ---------- 同步进度看板 ---------- */
App.reg('#/batch/board', '同步进度看板', function(){
  var b = DB.syncBatches[0];
  var html = UI.pageHead('同步进度看板', '实时展示批量同步进度、数据量核对与历史统计',
    '<button class="btn" onclick="App.go(\'#/sync/list\')">同步任务列表</button><button class="btn btn-primary" onclick="A.syncReport(\''+b.id+'\')">⇩ 最新核对报告</button>',
    '操作指引：看板实时汇总当前批次的表级进度、成功/失败/差异数与入仓数据量；趋势图展示近 7 日同步行数，右侧为各表耗时排名。可跳转批次明细逐表核对，或重新执行数据核对。');
  var pct = Math.round((b.ok+b.diff+b.fail)/b.total*100);
  html += UI.stateFlow([
    {k:'create', t:'批次创建',  done:true, d:'选表 · 自动建表分区'},
    {k:'run',    t:'同步执行',  on:true,   d:'进行中 '+pct+'%'},
    {k:'check',  t:'数据量核对', d:'完成后自动触发'},
    {k:'result', t:'核对完成',  d:'成功 / 差异 / 失败 → 报告'}
  ], 'run', null);
  html += UI.card('当前批次：'+b.id+'（'+b.srcName+' → '+b.target+'）',
    '<div class="grid grid-6">'
    +'<div class="stat-card"><div><div class="stat-num">'+b.total+'</div><div class="stat-label">总表数</div></div></div>'
    +'<div class="stat-card"><div><div class="stat-num" style="color:var(--success)">'+b.ok+'</div><div class="stat-label">成功</div></div></div>'
    +'<div class="stat-card"><div><div class="stat-num" style="color:var(--danger)">'+b.fail+'</div><div class="stat-label">失败</div></div></div>'
    +'<div class="stat-card"><div><div class="stat-num" style="color:var(--warn)">'+b.diff+'</div><div class="stat-label">差异</div></div></div>'
    +'<div class="stat-card"><div><div class="stat-num" style="font-size:17px">'+fmt(b.tgtRows)+'<span style="font-size:11px;color:var(--text-3)"> / '+fmt(b.srcRows)+' 行</span></div><div class="stat-label">入仓/源端数据量</div></div></div>'
    +'<div class="stat-card"><div style="flex:1"><div class="progress"><div class="bar" style="width:'+pct+'%"></div></div><div class="stat-label" style="margin-top:5px">进度 '+pct+'%</div></div></div></div>'
    + '<div style="display:flex;gap:8px;margin-top:10px"><button class="btn" onclick="App.go(\'#/sync/detail/'+b.id+'\')">查看批次明细</button><button class="btn" onclick="A.syncCheck(\''+b.id+'\')">执行数据核对</button></div>');
  html += UI.card('每日同步数据量趋势', '<div style="display:flex;gap:20px;flex-wrap:wrap"><div style="flex:1;min-width:320px">'+Charts.line({w:560,h:220,labels:['09-06','09-07','09-08','09-09','09-10','09-11','09-12'],series:[{name:'同步行数(万)',color:'#1668dc',data:[980,1050,1120,990,1180,1250,1250]}]})+'</div>'
    +'<div style="flex:1;min-width:280px">'+Charts.hbars([{name:'order_info',value:120,color:''},{name:'pay_log',value:95},{name:'user_info',value:45},{name:'coupon_record',value:60},{name:'member_level',value:22}])+'<div class="f-help" style="margin-top:6px">各表同步耗时排名（秒）</div></div></div>');
  html += UI.card('历史批次统计', UI.tbl({
    id:'t_hissync', rowKey:'id', pageSize:5, searchKeys:['id','srcName'],
    data:function(){ return DB.syncBatches; },
    cols:[{t:'批次',k:'id',render:function(r){return '<a class="mono" onclick="App.go(\'#/sync/detail/'+r.id+'\')">'+r.id+'</a>';}},
      {t:'链路',render:function(r){return UI.esc(r.srcName)+' → '+UI.esc(r.target);}},
      {t:'成功率',render:function(r){return Charts.ring(Math.round(r.ok/r.total*100), 46)+'<span style="font-size:11px">'+Math.round(r.ok/r.total*100)+'%</span>';}},
      {t:'状态',k:'status',render:function(r){return st(r.status);}}],
    ops:function(r){return '<a onclick="App.go(\'#/sync/detail/'+r.id+'\')">明细</a><a onclick="A.syncReport(\''+r.id+'\')">报告</a>';}
  }));
  return html;
});

/* ---------- ETL任务 ---------- */
App.reg('#/etl/list', 'ETL任务', function(){
  var html = UI.pageHead('批处理 ETL 任务',
    '可视化ETL设计器 / SQL脚本任务 / 脚本任务；配合 DAG 工作流实现定时调度、依赖编排、容错重试（UDF 一期不做）',
    '<button class="btn btn-primary" onclick="A.etlCreate()">+ 新建ETL任务</button>');
  html += UI.card('任务列表', UI.tbl({
    id:'t_etl', rowKey:'id', pageSize:8, searchKeys:['name','code','type','owner'], searchPh:'搜索任务名称/编码',
    filters:[{k:'type', label:'类型', options:[{v:'可视化ETL',t:'可视化ETL'},{v:'SQL任务',t:'SQL任务'},{v:'脚本任务',t:'脚本任务'}]}],
    data:function(){ return DB.etlTasks; },
    cols:[
      {t:'任务', k:'name', render:function(r){ return '<a onclick="App.go(\'#/etl/design/'+r.id+'\')"><b>'+UI.esc(r.name)+'</b></a><div class="mono" style="font-size:11px;color:var(--text-3)">'+r.code+'</div>'; }},
      {t:'类型', k:'type', render:function(r){ return tag(r.type, r.type==='可视化ETL'?'blue':r.type==='SQL任务'?'cyan':'purple'); }},
      {t:'调度', k:'cron', render:function(r){ return r.cron?'<span class="mono">'+r.cron+'</span>':'<span style="color:var(--text-3)">未配置</span>'; }},
      {t:'最近运行', k:'lastRun', render:function(r){ return r.lastRun==='-'?'-':st(r.lastRun); }},
      {t:'负责人', k:'owner'},
      {t:'状态', k:'status', render:function(r){ return r.status==='published'?st('published'):st('draft'); }}
    ],
    ops:function(r){
      return '<a onclick="App.go(\'#/etl/design/'+r.id+'\')">设计</a>'
        + '<a onclick="A.etlRun(\''+r.id+'\')">运行</a>'
        + '<a onclick="A.etlPub(\''+r.id+'\')">'+(r.status==='published'?'下线':'发布')+'</a>'
        + '<a class="danger" onclick="A.etlDel(\''+r.id+'\')">删除</a>';
    }
  }));
  return html;
});
A.etlCreate = function(){
  UI.drawer({title:'新建ETL任务', w:'w-lg', body:
    UI.fInput('任务名称', 'e_name', {req:true, ph:'如：清洗支付明细'})
    + UI.fInput('任务编码', 'e_code', {value:'etl_', help:'命名规范 NR-06：etl_[目标表]_[动作]'})
    + UI.fRadio('任务类型', 'e_type', [{v:'etl',t:'可视化ETL'},{v:'sql',t:'SQL任务'},{v:'script',t:'脚本任务（Python/Shell）'}], 'sql')
    + UI.fSelect('目标产出表', 'e_out', DB.models.map(function(m){return {v:m.code,t:m.code};}), {value:'dwd_order_pay_detail'}),
    onOk:function(){
      var t = UI.radioVal('e_type','sql');
      DB.etlTasks.push({id:'ETL'+String(DB.etlTasks.length+1).padStart(3,'0'), name:UI.val('e_name'), code:UI.val('e_code'), type:t==='etl'?'可视化ETL':t==='sql'?'SQL任务':'脚本任务', status:'draft', owner:DB.user.name, cron:'', lastRun:'-', updatedAt:'2026-09-12 22:40', sql:t==='sql'?'-- 编写SQL\nSELECT 1;':'', scriptLang:t==='script'?'Python':undefined});
      UI.toast('ETL任务已创建（草稿），可进入设计器编排', 'success');
    }});
};
A.etlRun = function(id){
  var t = DB.etlTasks.find(function(x){return x.id===id;});
  UI.toast('任务「'+t.name+'」提交运行 ...', 'info');
  setTimeout(function(){ t.lastRun='success'; UI.toast('任务运行成功，产出表已注册血缘', 'success'); App.resolve(); }, 1200);
};
A.etlPub = function(id){
  var t = DB.etlTasks.find(function(x){return x.id===id;});
  if(t.status==='published'){ t.status='draft'; UI.toast('任务已下线（草稿态）', 'info'); }
  else { t.status='published'; UI.toast('任务已发布，可被DAG工作流引用', 'success'); }
  App.resolve();
};
A.etlDel = function(id){
  var t = DB.etlTasks.find(function(x){return x.id===id;});
  UI.delRow(DB.etlTasks, 'id', id, t.name);
};

/* ============================================================
   可视化ETL设计器（DolphinScheduler 式三栏全屏）
   左：元件库（元组/转换/资源/逻辑判定/连接线） 拖拽入画布
   中：VC 画布（默认开始+结束节点，节点hover摘要、连线、自动排版）
   右：验证与测试面板（链路校验/试运行/输入输出预览）
   ============================================================ */
A.ETL_PALETTE = [
  {cat:'元组（输入/输出）', items:[
    {type:'source', name:'数据源表', icon:'⛁', color:'#0ea5e9', desc:'库表/流读取', summary:'选择已注册数据源中的库表作为输入'},
    {type:'target', name:'输出目标表', icon:'⛃', color:'#16a34a', desc:'写入目标', summary:'写入数仓目标表（append/overwrite/merge）'},
    {type:'kafka', name:'消息流', icon:'≡', color:'#7c3aed', desc:'Kafka Topic', summary:'订阅 Kafka Topic 作为流式输入'}]},
  {cat:'转换元件', items:[
    {type:'filter', name:'过滤', icon:'⧨', color:'#f59e0b', desc:'条件筛选行', summary:'按条件表达式筛选记录'},
    {type:'join', name:'Join 关联', icon:'⨝', color:'#8b5cf6', desc:'多表关联', summary:'inner/left/full 关联，支持多键'},
    {type:'agg', name:'聚合', icon:'Σ', color:'#d97706', desc:'分组汇总', summary:'group by + sum/count/avg…'},
    {type:'select', name:'字段选择', icon:'⇥', color:'#0ea5e9', desc:'列裁剪/改名', summary:'列裁剪、重命名、类型转换'},
    {type:'expr', name:'表达式', icon:'ƒ', color:'#2563eb', desc:'派生列', summary:'新增计算字段'},
    {type:'dedup', name:'去重', icon:'①', color:'#0891b2', desc:'按键去重', summary:'按主键去重保留首末条'},
    {type:'sort', name:'排序', icon:'↕', color:'#64748b', desc:'全局/局部排序', summary:'按字段升/降序'},
    {type:'split', name:'拆分', icon:'⑃', color:'#e5484d', desc:'一路分多路', summary:'按条件将数据流拆为多路（分支线）'},
    {type:'merge', name:'合并', icon:'⑉', color:'#059669', desc:'多路合一路', summary:'union 多路输入'},
    {type:'replace', name:'查找替换', icon:'⇄', color:'#db2777', desc:'码表映射', summary:'按字典/码表替换字段值'}]},
  {cat:'资源', items:[
    {type:'sql', name:'SQL 片段', icon:'⌨', color:'#334155', desc:'内嵌SQL', summary:'执行内嵌 SQL（多段传递变量）'},
    {type:'script', name:'脚本', icon:'⌨', color:'#334155', desc:'Python/Shell', summary:'调用脚本任务（M14 脚本库）'},
    {type:'udf', name:'自定义函数', icon:'ƒ', color:'#94a3b8', desc:'UDF（一期暂缓）', summary:'UDF 一期不做，排后迭代'}]},
  {cat:'逻辑控制', items:[
    {type:'if', name:'判定（IF）', icon:'◆', color:'#f59e0b', desc:'条件判定', summary:'按条件走不同分支（条件分支线）'},
    {type:'case', name:'多路分支（CASE）', icon:'◈', color:'#f59e0b', desc:'多分支', summary:'多条件多路分支'},
    {type:'depend', name:'跨流依赖', icon:'⛓', color:'#94a3b8', desc:'依赖其他流', summary:'依赖其他工作流实例成功（依赖线）'}]}
];

App.reg('#/etl/design/:id', 'ETL设计器', function(p){
  var t = DB.etlTasks.find(function(x){return x.id===p.id;});
  if(!t) return '<div class="empty">任务不存在</div>';
  A._etlCur = t;
  var isEtl = t.type==='可视化ETL';
  var head = '<div class="etl-topbar">'
    + '<div><a onclick="App.go(\'#/etl/list\')">← ETL任务</a> <b style="margin-left:8px;font-size:14.5px">'+UI.esc(t.name)+'</b>'
    + '<span class="tag" style="margin-left:8px">'+t.type+'</span><span class="mono" style="color:var(--text-3);font-size:12px;margin-left:8px">'+t.code+'</span></div>'
    + '<div style="display:flex;gap:8px">'
    + '<button class="btn btn-sm" onclick="UI.toast(\'参数引用检测通过：${biz_date}（内置）可用\',\'success\')">参数检测</button>'
    + '<button class="btn btn-sm" onclick="A.etlSave(\''+t.id+'\')">保存</button>'
    + '<button class="btn btn-sm" onclick="A.etlValidate()">✓ 校验</button>'
    + '<button class="btn btn-sm btn-primary" onclick="A.etlDryRun()">▶ 试运行</button>'
    + (t.status==='published'? '<button class="btn btn-sm" onclick="A.etlPub(\''+t.id+'\')">下线</button>':'<button class="btn btn-sm btn-success" onclick="A.etlPub(\''+t.id+'\')">发布</button>')
    + '</div></div>';

  if(!isEtl){
    return head + '<div class="card no-head" style="margin-top:12px"><div class="card-body">'
      + '<div class="editor-wrap"><div class="editor-toolbar"><b style="font-size:12.5px">'+(t.type==='脚本任务'?(t.scriptLang||'Python')+' 脚本':'SQL 编辑')+'</b><span style="flex:1"></span>'
      + '<button class="btn btn-sm" onclick="A.ideAiFmt()">✦ AI 优化</button><button class="btn btn-sm" onclick="UI.toast(\'SQL已格式化\',\'success\')">格式化</button><button class="btn btn-sm" onclick="UI.toast(\'参数引用检测：${biz_date} 可用\',\'success\')">参数检测</button><button class="btn btn-sm" onclick="UI.toast(\'产出表解析：ads_kpi_report（自动解析成功）\',\'success\')">解析产出表</button><button class="btn btn-primary btn-sm" onclick="A.etlRun(\''+t.id+'\')">▶ 运行</button></div>'
      + '<textarea class="editor-area" style="min-height:280px" id="etlSql">'+UI.esc(t.sql||t.script||'')+'</textarea></div>'
      + '<div style="margin-top:10px;color:var(--text-3);font-size:12px">提示：支持多段SQL顺序执行与变量传递；内置参数 ${biz_date} 等可直接引用（M12 参数配置）。</div>'
      + '</div></div>' + A._etlRunTable(t);
  }

  return head
    + '<div class="etl-main">'
    + '<div id="etlVcMount"></div>'
    + '<div class="etl-right">'
    +   '<div class="etl-right-h">验证与测试</div>'
    +   '<div class="etl-right-b">'
    +     '<div id="etlValidateBox"><div class="f-help" style="margin-bottom:8px">点击「✓ 校验」或右上角按钮进行链路校验：孤立节点/环路/断链/汇聚语义。</div></div>'
    +     '<div style="border-top:1px dashed var(--border);margin:10px 0"></div>'
    +     '<b style="font-size:12px">试运行</b>'
    +     '<div style="display:flex;gap:6px;margin:8px 0"><button class="btn btn-sm" onclick="A.etlSample()">输入抽样 10 行</button><button class="btn btn-sm btn-primary" onclick="A.etlDryRun()">▶ 运行</button></div>'
    +     '<div class="log-box" style="height:180px" id="etlRunLog"><span class="lg-info">ℹ 尚未执行。点击「▶ 运行」以图上逐节点点亮方式预演链路。</span></div>'
    +   '</div>'
    + '</div>'
    + '</div>' + A._etlRunTable(t);
});
A._etlRunTable = function(t){
  return UI.card('运行记录', UI.tbl({
    id:'t_etlrun', rowKey:'t', pageSize:5, searchKeys:['t'],
    data:function(){ return [{t:'2026-09-12 02:30', s:'success', d:'95s', rows:3980000},{t:'2026-09-11 02:30', s:'success', d:'92s', rows:3960000},{t:'2026-09-10 02:30', s:'failed', d:'18s', rows:0}]; },
    cols:[{t:'时间',k:'t'},{t:'结果',k:'s',render:function(r){return st(r.s);}},{t:'耗时',k:'d'},{t:'处理行数',render:function(r){return '<span class="mono">'+fmt(r.rows)+'</span>';}}],
    ops:function(r){ return '<a onclick="UI.toast(\'查看运行日志（stdout/调度日志）\',\'info\')">日志</a><a onclick="A.etlRun(\''+t.id+'\')">重新执行</a>'; }
  }));
};
/* ETL001 默认链路 → VC 节点数据 */
A.etlFlow = function(t){
  var defs = t.flow;
  if(defs) return defs;
  var ops = t.ops||[];
  var nodes = [{id:'start', name:'开始', type:'START', icon:'▶', color:'#16a34a', x:40, y:180, cat:'系统', summary:'流程入口（固定节点）', cfg:{}},
    {id:'end', name:'结束', type:'END', icon:'■', color:'#94a3b8', x:880, y:180, cat:'系统', summary:'流程出口（固定节点）', cfg:{}}];
  var edges = [];
  var prev = 'start';
  ops.forEach(function(o, i){
    var meta = null;
    A.ETL_PALETTE.forEach(function(c){ c.items.forEach(function(it){ if(it.type===o.type) meta=it; }); });
    nodes.push({id:'n_'+o.id, name:o.name, type:o.type, icon:(meta&&meta.icon)||'▣', color:(meta&&meta.color)||'#1668dc',
      x:40+(i+1)*150, y:180, cat:'算子', summary:(meta&&meta.summary)||o.name, cfg:{配置:o.cfg}});
    edges.push({from:prev, to:'n_'+o.id, kind:'flow'});
    prev = 'n_'+o.id;
  });
  edges.push({from:prev, to:'end', kind:'flow'});
  return {nodes:nodes, edges:edges};
};
A.etlInitVc = function(){
  var t = A._etlCur;
  var d = A.etlFlow(t);
  A._etlVc = VC.create({mount:'etlVcMount', nodes:d.nodes, edges:d.edges, palette:A.ETL_PALETTE, editable:true, height:620,
    legendExtra:[{c:'#16a34a', t:'开始/结束'}, {c:'#0ea5e9', t:'输入'}, {c:'#16a34a', t:'输出'}],
    onNodeClick:function(n, api){ A.etlNodeEdit(n, api); },
    onCanvasChange:function(){ A.etlValidate(false); }});
  setTimeout(function(){ A.etlValidate(false); }, 60);
};
App.onAfterRender(function(){ if(location.hash.indexOf('#/etl/design/')===0) A.etlInitVc(); });
A.etlNodeEdit = function(n, api){
  var isSys = n.type==='START'||n.type==='END';
  UI.drawer({title:'节点配置 - '+n.name, w:'w-lg', body:
    '<div class="tabs" id="etlNtTabs"><span class="tab on" onclick="A._ntTab(this,0)">① 输入输出</span><span class="tab" onclick="A._ntTab(this,1)">② 算子配置</span><span class="tab" onclick="A._ntTab(this,2)">③ 验证与业务逻辑</span></div>'
    + '<div id="nt0">'
    + UI.fInput('节点名称', 'nn_name', {value:n.name, req:true})
    + UI.fInput('输入（上游字段/表）', 'nn_in', {value:n.cfg['输入']||'上游节点输出全集', disabled:isSys})
    + UI.fInput('输出（下游消费字段/表）', 'nn_out', {value:n.cfg['输出']||(n.type==='target'? DB.models[1].code : '透传上游'), disabled:isSys})
    + UI.fInput('字段映射说明', 'nn_io', {value:n.inOut||'', ph:'如：pay_amt(元→分) · 新增 amt_fen', disabled:isSys})
    + '</div>'
    + '<div id="nt1" style="display:none">'
    + (isSys? '<div class="empty" style="padding:26px"><span class="e-ico">▣</span><p>系统固定节点，无需算子配置</p></div>'
      : UI.fTextarea('配置内容（JSON/表达式）', 'nn_cfg', {value:n.cfg['配置']||'（待配置）', rows:4, mono:true})
      + '<div class="f-help">'+({filter:'条件表达式，如 pay_amt > 0 AND bill_type != \'冲销\'', join:'left join dim_user on user_id', agg:'group by user_id, pay_date; sum(pay_amt) pay_amt', target:'写入模式：merge（幂等）/ append / overwrite', source:'数据源.库.表，如 greatdb_gdb.gdb_biz.user_info'}[n.type]||'算子参数定义')+'</div>')
    + '</div>'
    + '<div id="nt2" style="display:none">'
    + '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>验证规则：①配置非空 ②输入输出字段闭环 ③业务口径与指标定义一致。</span></div>'
    + UI.fTextarea('业务逻辑说明', 'nn_logic', {value:n.cfg['业务逻辑']||'', rows:3, ph:'描述该节点的业务口径、注意事项'})
    + '<button class="btn btn-sm" onclick="UI.toast(\'节点验证通过：配置完整，输入输出闭环 ✓\',\'success\')">▶ 验证此节点</button>'
    + '<button class="btn btn-sm" style="margin-left:6px" onclick="AI.show(\'节点「'+UI.esc(n.name)+'」AI 审查：\n· 配置完整 ✓\n· 建议输出字段补充注释\n· 与下游指标口径对齐 ✓\')">✦ AI 审查</button>'
    + '</div>',
    onOk:function(){
      if(isSys && UI.val('nn_name')===(n.name)) { /* 仅改名 */ }
      api.update(n.id, {name:UI.val('nn_name')||n.name, inOut:UI.val('nn_io'),
        cfg:Object.assign({}, n.cfg, isSys? {}:{'配置':UI.val('nn_cfg'),'输出':UI.val('nn_out'),'输入':UI.val('nn_in'),'业务逻辑':UI.val('nn_logic')}),
        summary:(n.type==='START'||n.type==='END')? n.summary : (({filter:'条件过滤', join:'多表关联', agg:'分组聚合', target:'写入目标表', source:'读取源表'}[n.type])||'算子')+' · '+(UI.val('nn_cfg')||'').slice(0,40)});
      UI.toast('节点配置已保存，摘要已更新（悬浮可见）', 'success');
    }});
};
A._ntTab = function(el, i){
  document.querySelectorAll('#etlNtTabs .tab').forEach(function(t,idx){ t.classList.toggle('on', idx===i); });
  [0,1,2].forEach(function(x){ var d=document.getElementById('nt'+x); if(d) d.style.display = x===i? '':'none'; });
};
A.etlValidate = function(quiet){
  if(!A._etlVc) return;
  var errs = VC.validate(A._etlVc);
  var box = document.getElementById('etlValidateBox'); if(!box) return;
  box.innerHTML = errs.length? errs.map(function(e){
    return '<div class="banner '+(e.level==='error'?'banner-danger':'banner-warn')+'" style="margin-bottom:6px;padding:8px 11px"><span class="b-ico">'+(e.level==='error'?'✗':'⚠')+'</span><span style="font-size:12px">'+UI.esc(e.msg)+'</span></div>';
  }).join('') : '<div class="banner banner-success" style="padding:8px 11px"><span class="b-ico">✓</span><span style="font-size:12px">链路校验通过：无孤立节点、无断链、流程收敛</span></div>';
  if(!quiet) UI.toast(errs.filter(function(e){return e.level==='error';}).length? '校验发现 '+errs.length+' 个问题':'链路校验通过', errs.length?'warn':'success');
};
A.etlDryRun = function(){
  if(!A._etlVc){ UI.toast('设计器未就绪','warn'); return; }
  A.etlValidate(true);
  var d = VC.getData(A._etlVc);
  var log = document.getElementById('etlRunLog');
  if(!log) return;
  var lines = ['<span class="lg-info">ℹ 试运行（抽样 10 行）· '+new Date().toLocaleTimeString()+'</span>'];
  var lv = VC.autoPos(d.nodes, d.edges); /* no-op 借 topo */
  var order = [];
  (function(){ /* 拓扑输出顺序 */
    var indeg = {}, out = {};
    d.nodes.forEach(function(n){ indeg[n.id]=0; out[n.id]=[]; });
    d.edges.forEach(function(e){ out[e.from].push(e.to); indeg[e.to]++; });
    var q = d.nodes.filter(function(n){return !indeg[n.id];}).map(function(n){return n.id;});
    while(q.length){ var c=q.shift(); order.push(c); out[c].forEach(function(t2){ if(--indeg[t2]===0) q.push(t2); }); }
  })();
  log.innerHTML = lines.join('<br>');
  order.forEach(function(id, i){
    setTimeout(function(){
      var n = d.nodes.find(function(x){return x.id===id;});
      if(n){ VC.updateNode(A._etlVc, id, {status:'success'}); }
      if(d.edges) d.edges.forEach(function(e){ if(e.from===id){ e.run=true; } });
      log.insertAdjacentHTML('beforeend','<br><span class="lg-ok">✓ ['+String(i+1).padStart(2,'0')+'] '+UI.esc(n?n.name:id) +' 完成 · 10 行 · 12ms</span>');
      log.scrollTop = log.scrollHeight;
    }, 350*(i+1));
  });
  setTimeout(function(){
    log.insertAdjacentHTML('beforeend','<br><span class="lg-ok">✔ 试运行成功：输出预览 10 行已生成，血缘预注册 dwd_order_pay_detail</span>');
    log.scrollTop = log.scrollHeight;
    VC.setData(A._etlVc, d);
  }, 350*(order.length+1));
};
A.etlSample = function(){
  UI.drawer({title:'输入抽样（10 行）', w:'w-xl', body:
    UI.tbl({id:'t_sample', rowKey:'i', pageSize:5,
      data:function(){ return [1,2,3,4,5,6,7,8,9,10].map(function(i){ return {i:i, order_no:'SO2026'+String(9000+i), user_id:'U'+String(1000+i*7), pay_amt:(Math.random()*900+20).toFixed(2), pay_type:['wxpay','alipay','union'][i%3], pay_date:'2026-09-12'}; }); },
      cols:[{t:'#',k:'i'},{t:'order_no',k:'order_no'},{t:'user_id',k:'user_id'},{t:'pay_amt',k:'pay_amt'},{t:'pay_type',k:'pay_type'},{t:'pay_date',k:'pay_date'}]
    })});
};
A.etlSave = function(id){
  if(A._etlVc){
    var d = VC.getData(A._etlVc);
    A._etlCur.flow = d;
    A._etlCur.ops = d.nodes.filter(function(n){return n.cat==='算子';}).map(function(n){ return {id:n.id.replace('n_',''), type:n.type, name:n.name, cfg:(n.cfg&&n.cfg['配置'])||'（待配置）'}; });
  }
  UI.toast('已保存设计稿（节点 '+((A._etlCur.flow&&A._etlCur.flow.nodes)||[]).length+' 个）', 'success');
};
})();

