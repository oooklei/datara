/* ============================================================
   M09 元数据管理（P0：目录/采集/血缘/资产地图/标签）
   ============================================================ */
(function(){
var LAYERX = {ODS:40, DIM:250, DWD:460, DWS:670, ADS:880};

/* ---- 元数据目录 ---- */
App.reg('#/meta/catalog', '元数据目录', function(){
  var html = UI.pageHead('元数据目录',
    '全仓表级资产目录：主题域/分层导航 · 资产检索 · 表详情（结构/样例/血缘/标签） · 与采集任务联动更新',
    '<button class="btn btn-primary" onclick="App.go(\'#/meta/collect\')">采集任务管理</button>'
    +'<button class="btn" onclick="App.go(\'#/meta/lineage\')">血缘分析</button>'
    +'<button class="btn" onclick="UI.toast(\'目录已重新统计：5 个主题域 / '+DB.metaTables.length+' 张表\',\'success\');App.resolve()">刷新统计</button>');
  var domainNav = '<div style="flex:0 0 230px">'
    + UI.card('主题域导航', '<div class="tree">'
      + '<div class="t-node on"><span class="caret open">▶</span><span class="t-ico">◈</span><span>全部（'+DB.metaTables.length+'）</span></div>'
      + DB.bizDomains.map(function(d){
        var cnt = DB.metaTables.filter(function(t){return t.domain===d.name;}).length;
        return '<div class="t-children"><div class="t-node"><span class="caret"></span><span class="t-ico" style="color:'+d.color+'">◆</span><span>'+d.name+'</span><span style="margin-left:auto;font-size:11px;color:var(--text-3)">'+cnt+'表</span></div></div>';
      }).join('') + '</div>')
    + UI.card('分层视图', '<div style="display:flex;flex-direction:column;gap:8px">'
      + ['ODS','DIM','DWD','DWS','ADS'].map(function(l){
        var cnt = DB.metaTables.filter(function(t){return t.layer===l;}).length;
        return '<div style="display:flex;justify-content:space-between;padding:8px 12px;border-radius:7px;background:var(--bg);font-size:12.5px"><b>'+l+'</b><span style="color:var(--text-3)">'+cnt+' 张</span></div>';
      }).join('') + '</div>')
    + '</div>';
  var list = '<div style="flex:1;min-width:0">'+UI.card('数据表资产',
    UI.tbl({id:'t_meta', rowKey:'id', pageSize:8, selectable:true, searchKeys:['name','domain','layer','owner','desc'], searchPh:'搜索表名/描述/负责人',
      filters:[
        {k:'layer', label:'分层', options:['ODS','DIM','DWD','DWS','ADS'].map(function(l){return {v:l,t:l};})},
        {k:'domain', label:'主题域', options:DB.bizDomains.map(function(d){return {v:d.name,t:d.name};})},
        {k:'yesterdayOk', label:'昨日产出', options:[{v:true,t:'正常'},{v:false,t:'异常'}]}
      ],
      data:function(){ return DB.metaTables; },
      cols:[
        {t:'表名', k:'name', sortable:true, render:function(r){
          return '<div><a onclick="A.metaDetail(\''+r.id+'\')"><b class="mono">'+r.name+'</b></a><div style="color:var(--text-3);font-size:11px">'+UI.esc(r.desc)+'</div></div>';}},
        {t:'分层', k:'layer', render:function(r){return tag(r.layer, r.layer==='ODS'?'cyan':r.layer==='DWD'?'blue':r.layer==='DWS'?'purple':r.layer==='ADS'?'green':'orange');}},
        {t:'主题域', k:'domain'},
        {t:'行数', k:'rows', sortable:true, render:function(r){return fmt(r.rows);}},
        {t:'大小', k:'size'},
        {t:'标签', render:function(r){return (r.tags||[]).map(function(t){var tg=DB.metaTags.find(function(x){return x.name===t;});return '<span class="tag" style="background:'+(tg?tg.color:'#f1f3f7')+'22;color:'+(tg?tg.color:'var(--text-2)')+'">'+t+'</span>';}).join(' ')||'-';}},
        {t:'昨日产出', render:function(r){return r.yesterdayOk? '<span class="st st-green"><i class="dot"></i>正常</span>' : '<span class="st st-red"><i class="dot"></i>异常</span>';}},
        {t:'负责人', k:'owner'}
      ],
      ops:function(r){
        return '<a onclick="A.metaDetail(\''+r.id+'\')">详情</a>'
          +'<a onclick="App.go(\'#/meta/lineage\')">血缘</a>'
          +'<a onclick="App.go(\'#/ide\')">查询</a>';
      }})) + '</div>';
  html += '<div style="display:flex;gap:16px;align-items:flex-start">'+domainNav+list+'</div>';
  return html;
});

/* 表详情抽屉 */
A.metaDetail = function(id){
  var t = DB.metaTables.find(function(x){return x.id===id;});
  if(!t) return;
  var lineage = DB.tableLineage.filter(function(l){return l.from===t.name||l.to===t.name;});
  var body = UI.tabs('mdTab', [{label:'资产概览'},{label:'字段结构'},{label:'样例数据'},{label:'血缘关系（'+lineage.length+'）'},{label:'标签'}], 0)
    + '<div id="mdTabBody"></div>';
  UI.drawer({title:'资产详情 - '+t.name, w:'w-xl', body:body, footer:'<button class="btn" onclick="UI.closeDrawer()">关闭</button><button class="btn btn-primary" onclick="UI.closeDrawer();App.go(\'#/ide\')">在IDE中查询</button>'});
  UI._tabCb['mdTab'] = function(i){ A._mdTab(i, t, lineage); };
  A._mdTab(0, t, lineage);
};
A._mdTab = function(i, t, lineage){
  var b = document.getElementById('mdTabBody');
  if(i===0){
    b.innerHTML = UI.desc([
      ['表名','<span class="mono">'+t.name+'</span>'],['分层', tag(t.layer,'blue')],['主题域', t.domain],
      ['行数', fmt(t.rows)],['大小', t.size],['负责人', t.owner],
      ['描述', t.desc],['昨日产出', t.yesterdayOk? st('success') : st('failed')],
      ['标签', (t.tags||[]).join('、')||'-'],
      ['上游表', lineage.filter(function(l){return l.to===t.name;}).length+' 张'],
      ['下游表', lineage.filter(function(l){return l.from===t.name;}).length+' 张']
    ]);
  }
  if(i===1){
    var m = DB.models.find(function(x){return x.code===t.name;});
    var fs = m? m.fields.map(function(f){return {n:f.n,t:f.t+(f.len||''),c:f.cmt,pk:f.pk};}) :
      [{n:'id',t:'BIGINT',c:'主键',pk:true},{n:'name',t:'VARCHAR(100)',c:'名称',pk:false},{n:'create_time',t:'DATETIME',c:'创建时间',pk:false},{n:'dt',t:'DATE',c:'分区字段',pk:false}];
    b.innerHTML = UI.tbl({id:'t_mdf'+t.id, rowKey:'n', pageSize:10, searchKeys:['n','c'], data:function(){return fs;},
      cols:[{t:'字段', k:'n', render:function(r){return '<span class="mono">'+r.n+'</span>'+(r.pk?' <span class="tag tag-red" style="height:16px;font-size:10px">PK</span>':'');}},
            {t:'类型', k:'t'},{t:'注释', k:'c'}], ops:null});
  }
  if(i===2){
    var keys = t.sample.length? Object.keys(t.sample[0]) : [];
    b.innerHTML = '<div class="table-wrap"><table class="tbl"><thead><tr>'+keys.map(function(k){return '<th>'+k+'</th>';}).join('')+'</tr></thead><tbody>'
      + t.sample.map(function(row){ return '<tr>'+keys.map(function(k){return '<td><span class="mono">'+UI.esc(row[k]==null?'NULL':row[k])+'</span></td>';}).join('')+'</tr>'; }).join('')
      + '</tbody></table></div><div class="lock-tip">仅展示前 '+t.sample.length+' 行样例（敏感字段已脱敏）</div>';
  }
  if(i===3){
    b.innerHTML = UI.timeline(lineage.map(function(l, idx){
      var isUp = l.to===t.name;
      return {cls:isUp?'ok':'', title:(isUp?'上游：':'下游：')+l.task, time:l.wf,
        body:'<span class="mono">'+(isUp? l.from : l.to)+'</span> → '+(isUp? t.name : '')+''};
    }).map(function(x){return x;})) || '<div class="empty">无血缘</div>';
    b.innerHTML += '<button class="btn" style="margin-top:8px" onclick="UI.closeDrawer();App.go(\'#/meta/lineage\')">打开血缘分析图</button>';
  }
  if(i===4){
    b.innerHTML = DB.metaTags.map(function(tg){
      var on = (t.tags||[]).indexOf(tg.name)>=0;
      return '<label style="display:flex;gap:8px;align-items:center;padding:8px 10px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px;cursor:pointer"><input type="checkbox" class="md-tag" value="'+tg.name+'" '+(on?'checked':'')+'><span class="tag" style="background:'+tg.color+'22;color:'+tg.color+'">'+tg.name+'</span><span style="font-size:11.5px;color:var(--text-3)">'+tg.cat+' · '+UI.esc(tg.desc)+'</span></label>';
    }).join('') + '<button class="btn btn-primary" onclick="A.metaTagSave(\''+t.id+'\')">保存标签</button>';
  }
};
A.metaTagSave = function(id){
  var t = DB.metaTables.find(function(x){return x.id===id;});
  var vals = Array.prototype.map.call(document.querySelectorAll('.md-tag:checked'), function(e){return e.value;});
  t.tags = vals;
  DB.metaTags.forEach(function(tg){ tg.tables = tg.tables.filter(function(x){return x!==id;}); vals.forEach(function(v){ if(tg.name===v) tg.tables.push(id); }); tg.cnt = tg.tables.length; });
  UI.toast('「'+t.name+'」标签已更新', 'success'); A._mdTab(4, t, DB.tableLineage.filter(function(l){return l.from===t.name||l.to===t.name;}));
};

/* ---- 采集任务 ---- */
App.reg('#/meta/collect', '采集任务', function(){
  var html = UI.pageHead('元数据采集任务',
    '定时/触发式采集技术元数据（库表结构）、业务元数据（主题域标签）与操作元数据（调度依赖、产出关系），采集结果自动更新目录与血缘',
    '<button class="btn btn-primary" onclick="A.mcCreate()">+ 新建采集任务</button>');
  html += '<div class="grid grid-4" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#1668dc">⇩</span><div><div class="stat-num">'+DB.collectTasks.length+'</div><div class="stat-label">采集任务（启用 '+DB.collectTasks.filter(function(t){return t.status==='enabled';}).length+'）</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">▤</span><div><div class="stat-num">'+DB.metaTables.length+'</div><div class="stat-label">已纳管表</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#7c3aed">⑃</span><div><div class="stat-num">'+DB.tableLineage.length+'</div><div class="stat-label">表级血缘关系</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#d97706">⚑</span><div><div class="stat-num">'+DB.collectTasks.filter(function(t){return t.lastResult==='running';}).length+'</div><div class="stat-label">采集中</div></div></div></div>';
  html += UI.card('采集任务列表', UI.tbl({
    id:'t_mc', rowKey:'id', pageSize:8, searchKeys:['name','scope'], searchPh:'搜索任务/范围',
    filters:[{k:'status', label:'状态', options:[{v:'enabled',t:'启用'},{v:'disabled',t:'停用'}]}],
    data:function(){ return DB.collectTasks; },
    cols:[
      {t:'任务', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+UI.esc(r.scope)+'</div>';}},
      {t:'类型', k:'type', render:function(r){return tag(r.type, r.type==='定时'?'blue':'purple');}},
      {t:'调度周期', k:'cron', render:function(r){return '<span class="mono">'+r.cron+'</span>';}},
      {t:'最近采集', k:'lastRun'},
      {t:'结果', render:function(r){return st(r.lastResult==='success'?'success':r.lastResult==='running'?'running':r.lastResult);}},
      {t:'纳管表', k:'tables', render:function(r){return r.tables? fmt(r.tables)+' 张':'-';}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.mcRun(\''+r.id+'\')">立即采集</a>'
        +'<a onclick="A.mcLog(\''+r.id+'\')">日志</a>'
        +'<a onclick="A.mcEdit(\''+r.id+'\')">编辑</a>'
        +'<a onclick="UI.toggleStatus(DB.collectTasks.find(function(x){return x.id===\''+r.id+'\'}))">'+(r.status==='enabled'?'停用':'启用')+'</a>'
        +'<a class="danger" onclick="UI.delRow(DB.collectTasks, \'id\', \''+r.id+'\', \''+r.name+'\')">删除</a>';
    }}));
  return html;
});
A.mcFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('任务名称', 'mc_name', {value:d.name, req:true})
    + UI.fSelect('采集数据源', 'mc_ds', DB.datasources.map(function(x){return {v:x.id, t:x.name};}), {value:d.ds||'DS006'})
    + UI.fInput('采集范围', 'mc_scope', {value:d.scope, ph:'如：Doris-分析集群：dw_olap全部库表', full:true})
    + UI.fSelect('采集类型', 'mc_type', [{v:'定时',t:'定时采集'},{v:'触发式',t:'触发式（任务产出联动）'}], {value:d.type||'定时'})
    + UI.fInput('Cron 表达式', 'mc_cron', {value:d.cron||'0 0 1 * * ?', help:'定时类型必填，触发式自动关联 DAG 产出事件'})
    + UI.fSwitch('采集后自动更新血缘与目录', 'mc_auto', true, '基于调度操作元数据自动生成表级/字段级血缘')
    + '</div>';
};
A.mcCreate = function(){
  UI.drawer({title:'新建采集任务', w:'w-lg', body:A.mcFormFields({}),
    onOk:function(){
      var name = UI.val('mc_name');
      if(!name){ UI.toast('请填写任务名称', 'warn'); return false; }
      DB.collectTasks.push({id:'MC'+String(DB.collectTasks.length+1).padStart(3,'0'), name:name, scope:UI.val('mc_scope'), type:UI.val('mc_type'), cron:UI.val('mc_cron'), lastRun:'-', lastResult:'waiting', tables:0, status:'enabled'});
      UI.toast('采集任务已创建并启用', 'success');
    }});
};
A.mcEdit = function(id){
  var d = DB.collectTasks.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑采集任务 - '+d.name, w:'w-lg', body:A.mcFormFields(d), onOk:function(){
    Object.assign(d, {name:UI.val('mc_name'), scope:UI.val('mc_scope'), type:UI.val('mc_type'), cron:UI.val('mc_cron')});
    UI.toast('采集任务已保存', 'success');
  }});
};
A.mcRun = function(id){
  var d = DB.collectTasks.find(function(x){return x.id===id;});
  UI.toast('正在执行采集「'+d.name+'」...', 'info');
  d.lastResult = 'running';
  setTimeout(function(){
    var n = Math.floor(5+Math.random()*30);
    d.lastResult='success'; d.lastRun=now+' 22:4'+Math.floor(Math.random()*10); d.tables=(d.tables||0)+n;
    UI.toast('采集完成：新增/更新 '+n+' 张表元数据，血缘已同步更新', 'success'); App.resolve();
  }, 1200);
  App.resolve();
};
A.mcLog = function(id){
  var d = DB.collectTasks.find(function(x){return x.id===id;});
  UI.modal({title:'采集日志 - '+d.name, w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    '<div class="mono" style="background:#0d1424;color:#9fb2d0;border-radius:8px;padding:14px;font-size:11.5px;line-height:1.9">'
    +'['+d.lastRun+'] INFO  连接数据源成功（'+UI.esc(d.scope)+'）<br>'
    +'['+d.lastRun+'] INFO  扫描库表：2 个库 / '+(d.tables||12)+' 张表 / 96 个字段<br>'
    +'['+d.lastRun+'] INFO  技术元数据入库：表名、字段、类型、注释、行数、大小<br>'
    +'['+d.lastRun+'] INFO  操作元数据入库：调度依赖 '+Math.floor(2+Math.random()*6)+' 条、产出关系 '+Math.floor(2+Math.random()*5)+' 条<br>'
    +'['+d.lastRun+'] INFO  业务元数据：主题域标签自动归类完成<br>'
    +'['+d.lastRun+'] OK    采集完成，目录与血缘已更新</div>'});
};

/* ---- 血缘分析（增强：分析口径切换 + 任务流图示例 + 血缘走向） ---- */
A._linScope = 'flow';
A._linWf = 'WF001';
A._linTbl = 'dwd_order_pay_detail';
A._LIN_LAYER_C = {ODS:'#0891b2', DIM:'#d97706', DWD:'#1668dc', DWS:'#7c3aed', ADS:'#16a34a'};
A._LIN_NODE_T = {
  'ETL节点':{i:'⇄', c:'#1668dc'}, 'SQL节点':{i:'⌘', c:'#7c3aed'}, '脚本节点':{i:'⚙', c:'#d97706'},
  '子工作流':{i:'⧉', c:'#0891b2'}, '依赖检查':{i:'⏳', c:'#94a3b8'}
};
A._LIN_FLOW_LOGIC = {
  'ods_gdb_biz_trade_order':'sync: 全量抽取 gdb_main.trade_order → truncate+load 幂等写入',
  'dwd_order_pay_detail':'clean: 订单×支付 join → 过滤 status≠05 → pay_amount=amount-discount',
  'dws_pay_summary_daily':'agg: group by stat_date,channel · sum(pay_amount), count(distinct user_id)',
  'ads_kpi_report':'window: 近7天滚动求和 · 拼接经营KPI宽表',
  'dim_user':'scd: 全量覆盖更新 · gender/user_level 编码转译',
  'dim_product':'sync: merge on product_id 增量合并',
  'ads_daily_report':'assemble: 拼接KPI宽表 + 日报模板字段',
  'ods_oracle_gl_voucher':'sync: Oracle ERP 凭证全量接入',
  'dwd_gl_voucher_detail':'clean: 借贷平衡校验 · 科目编码标准化'
};
A._LIN_CALIBER = {
  'dwd_order_pay_detail':'pay_status=1 有效支付 · pay_amount=amount-discount',
  'dws_pay_summary_daily':'sum(pay_amount) group by stat_date,channel',
  'ads_kpi_report':'近7天滚动求和 · 不含退款',
  'dim_user':'全量覆盖 · 编码转译（C-003）',
  'dim_product':'merge on product_id',
  'ads_daily_report':'日报模板字段拼接'
};
A._linLayerOf = function(t){
  var g = DB.lineageGraph.nodes.filter(function(n){return n.id===t;})[0];
  if(g) return g.layer;
  var m = DB.metaTables.filter(function(x){return x.name===t;})[0];
  if(m) return m.layer;
  var p = String(t||'').split('_')[0].toLowerCase();
  return {ods:'ODS', dim:'DIM', dwd:'DWD', dws:'DWS', ads:'ADS'}[p] || 'DWD';
};
A._linTblSummary = function(t){
  var layer = A._linLayerOf(t);
  var ups = DB.tableLineage.filter(function(l){return l.to===t;}).map(function(l){return l.task;});
  var type = {ODS:'原样同步/接入', DIM:'维度加工', DWD:'清洗·明细加工', DWS:'聚合汇总', ADS:'应用装配'}[layer] || '加工';
  return '来源任务：'+(ups.length? ups.join('、') : '源端接入')+'；转换类型：'+type+'；口径：'+(A._LIN_CALIBER[t]||'按任务定义（演示）');
};
A._linScopeSeg = function(){
  var defs = [['flow','按任务流'],['table','按表'],['field','按字段']];
  return '<div style="display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;vertical-align:middle">'
    + defs.map(function(x){
      var on = A._linScope===x[0];
      return '<span onclick="A.linScope(\''+x[0]+'\')" style="padding:6px 18px;font-size:12.5px;cursor:pointer;user-select:none;'+(on?'background:var(--primary);color:#fff;font-weight:600':'background:#fff;color:var(--text-2)')+'">'+x[1]+'</span>';
    }).join('') + '</div>';
};
A.linScope = function(s){
  A._linScope = s;
  var bar = document.getElementById('linScopeBar'); if(bar) bar.innerHTML = A._linScopeSeg();
  var tip = document.getElementById('linScopeTip');
  if(tip) tip.innerHTML = {flow:'上栏任务流图定位加工环节，下栏查看该流产出表的血缘走向', table:'下栏高亮所选表的直接上游/下游', field:'下栏展示字段级映射清单（含加工逻辑）'}[s];
  A._linWalkRender();
};
A.linWfChange = function(){
  var s = document.getElementById('linWfSel'); if(s) A._linWf = s.value;
  A._linFlowRender();
  if(A._linScope==='flow') A._linWalkRender();
};
A.linTblChange = function(){
  var s = document.getElementById('linTblSel'); if(s) A._linTbl = s.value;
  A._linWalkRender();
};
A._linFlowRender = function(){
  var mount = document.getElementById('linFlowMount'); if(!mount) return;
  var wf = DB.workflows.filter(function(w){return w.id===A._linWf;})[0] || DB.workflows[0];
  A._linWf = wf.id;
  var nodes = wf.nodesDetail.map(function(nd){
    var m = A._LIN_NODE_T[nd.type] || {i:'▣', c:'#1668dc'};
    return {id:nd.id, name:nd.name, type:nd.type, icon:m.i, color:m.c,
      summary: A._LIN_FLOW_LOGIC[nd.outTable] || (nd.type+' · 产出 '+(nd.outTable||'无')),
      cfg:{'产出表':nd.outTable||'-', '重试':nd.retry+' 次', '参考时长':nd.dur}, x:0, y:0};
  });
  var edges = [];
  wf.nodesDetail.forEach(function(nd){ (nd.dep||[]).forEach(function(dp){ edges.push({from:dp, to:nd.id, kind:'flow'}); }); });
  VC.autoPos(nodes, edges);
  if(!A._linFlowVc || !document.getElementById(A._linFlowVc)){
    A._linFlowVc = VC.create({mount:'linFlowMount', nodes:nodes, edges:edges, editable:false, mode:'view', height:320,
      legendExtra:[{c:'#1668dc', t:'ETL/同步'},{c:'#7c3aed', t:'SQL 加工'}],
      onNodeClick:function(n){ A._linFlowNode(n, wf); }});
  } else {
    VC.setData(A._linFlowVc, {nodes:nodes, edges:edges});
  }
  var sel = document.getElementById('linWfSel'); if(sel) sel.value = A._linWf;
  var stt = document.getElementById('linFlowStats');
  if(stt) stt.innerHTML = wf.id+' '+UI.esc(wf.name)+' · '+UI.esc(wf.cron)+' · 节点 '+nodes.length+' · 连线 '+edges.length+' · hover/点击节点查看转换与组装逻辑';
};
A._linFlowNode = function(n, wf){
  var downs = wf.nodesDetail.filter(function(nd){ return (nd.dep||[]).indexOf(n.id)>=0; }).map(function(nd){return nd.name;});
  UI.modal({title:'转换与组装逻辑 - '+UI.esc(n.name), w:'w-md',
    footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="UI.closeModal();App.go(\'#/dag/list\')">查看工作流</button>',
    body: UI.desc([['所属工作流', wf.id+' '+UI.esc(wf.name)], ['节点类型', n.type], ['产出表', '<span class="mono">'+UI.esc(n.cfg['产出表'])+'</span>'],
      ['转换/组装逻辑', '<span class="mono" style="font-size:11.5px">'+UI.esc(n.summary)+'</span>'],
      ['下游节点', downs.length? downs.map(UI.esc).join('、') : '无']])
    + '<div class="lock-tip">转换逻辑由 ETL 表达式/SQL 算子解析自动登记，可在 IDE 中查看脚本原文。</div>'});
};
A._linWalkRender = function(){
  var body = document.getElementById('linWalkBody'); if(!body) return;
  var head = document.getElementById('linWalkHead');
  if(A._linScope==='field'){
    if(head) head.innerHTML = '<div class="dag-legend">字段级映射：目标字段 ← 上游字段 · 来源：ETL 表达式算子与 SQL 解析（点击「链路」查看完整加工链）</div>';
    body.innerHTML = A._linFieldList();
    return;
  }
  var d = A._linScope==='flow'? A._linWalkFlow() : A._linWalkTable();
  if(head) head.innerHTML = d.head;
  body.innerHTML = '<div id="linWalkMount"></div>';
  if(!A._linWalkVc || !document.getElementById(A._linWalkVc)){
    A._linWalkVc = VC.create({mount:'linWalkMount', nodes:d.nodes, edges:d.edges, editable:false, mode:'view', height:380, legend:false,
      onNodeClick:function(n){ A._linWalkNode(n); }});
  } else {
    VC.setData(A._linWalkVc, {nodes:d.nodes, edges:d.edges});
  }
  if(A._linScope==='table' && d.selId) VC.highlight(A._linWalkVc, d.selId);
};
A._linWalkFlow = function(){
  var wf = DB.workflows.filter(function(w){return w.id===A._linWf;})[0] || DB.workflows[0];
  var wfn = 'WF-'+wf.name;
  var outs = wf.nodesDetail.map(function(nd){return nd.outTable;}).filter(function(t){return t && t!=='-';});
  var lines = DB.tableLineage.filter(function(l){ return l.wf===wfn || (l.wf==='未入工作流' && outs.indexOf(l.to)>=0); });
  var nodes = [], edges = [], seen = {};
  function addNode(t){
    if(seen[t]) return; seen[t] = 1;
    var layer = A._linLayerOf(t);
    var up = DB.tableLineage.filter(function(l){return l.to===t;}).length;
    var dn = DB.tableLineage.filter(function(l){return l.from===t;}).length;
    nodes.push({id:t, name:t, type:layer+' 表', icon:'▤', color:A._LIN_LAYER_C[layer]||'#8c94a6',
      summary:A._linTblSummary(t), cfg:{'分层':layer, '全仓上游':up+' 张', '全仓下游':dn+' 张'}, x:0, y:0});
  }
  lines.forEach(function(l){ addNode(l.from); addNode(l.to); edges.push({from:l.from, to:l.to, kind:'flow', label:l.task.split(' (')[0]}); });
  if(!nodes.length) outs.forEach(addNode);
  VC.autoPos(nodes, edges);
  var head = '<div class="dag-legend">'
    + '<span>任务流 <b>'+wf.id+' '+UI.esc(wf.name)+'</b> 的表级血缘走向</span>'
    + '<span style="margin-left:auto">表 '+nodes.length+' · 血缘关系 '+edges.length+' · 边标签=产出任务 · hover 查看来源任务/转换类型/口径</span></div>';
  return {nodes:nodes, edges:edges, head:head};
};
A._linWalkTable = function(){
  var t = A._linTbl;
  var ups = {}, downs = {};
  DB.tableLineage.forEach(function(l){ if(l.to===t) ups[l.from]=1; if(l.from===t) downs[l.to]=1; });
  var nodes = DB.lineageGraph.nodes.map(function(n){
    var role = n.id===t? '当前表' : (ups[n.id]? '上游' : (downs[n.id]? '下游' : ''));
    var color = n.id===t? '#e5484d' : (ups[n.id]? '#0891b2' : (downs[n.id]? '#16a34a' : '#a8b6cc'));
    var mt = DB.metaTables.filter(function(x){return x.name===n.id;})[0];
    return {id:n.id, name:n.id, type:n.layer+' 表'+(role? ' · '+role:''), icon:'▤', color:color,
      summary:A._linTblSummary(n.id), cfg:{'与当前表':role||'-', '主题域':mt? mt.domain:'-'}, x:0, y:0};
  });
  var edges = DB.lineageGraph.edges.map(function(e){ return {from:e[0], to:e[1], kind:'flow'}; });
  VC.autoPos(nodes, edges);
  var head = '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:9px 13px;border-bottom:1px solid var(--border);font-size:11.5px;color:var(--text-2)">'
    + '<span>目标表</span><select class="sel" style="width:auto" id="linTblSel" onchange="A.linTblChange()">'
    + DB.lineageGraph.nodes.map(function(n){ return '<option value="'+n.id+'"'+(n.id===t?' selected':'')+'>'+n.id+'</option>'; }).join('')
    + '</select>'
    + '<span><i class="lg-dot" style="background:#e5484d;display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:4px;vertical-align:-1px"></i>当前表</span><span><i class="lg-dot" style="background:#0891b2;display:inline-block;width:9px;height:9px;border-radius:3px;margin:0 4px 0 8px;vertical-align:-1px"></i>上游 '+Object.keys(ups).length+'</span><span><i class="lg-dot" style="background:#16a34a;display:inline-block;width:9px;height:9px;border-radius:3px;margin:0 4px 0 8px;vertical-align:-1px"></i>下游 '+Object.keys(downs).length+'</span>'
    + '<span style="margin-left:auto;color:var(--text-3)">hover 节点查看转换与组装逻辑</span></div>';
  return {nodes:nodes, edges:edges, head:head, selId:t};
};
A._linFieldList = function(){
  var demo = {
    'dwd_order_pay_detail.pay_status':[{from:'ods_gdb_biz_trade_order.status', transform:'编码转译：01待支付/02已支付 → 0/1（代码标准 C-006）'}],
    'dim_user.user_level':[{from:'ods_gdb_biz_user_info.user_level', transform:'直接映射（用户等级代码标准 C-003 转译）'}]
  };
  var rows = Object.keys(DB.fieldLineage).map(function(k){ return {k:k, ups:DB.fieldLineage[k]}; })
    .concat(Object.keys(demo).map(function(k){ return {k:k, ups:demo[k], demo:true}; }));
  return UI.tbl({id:'t_linw', rowKey:'k', pageSize:8, searchKeys:['k'], searchPh:'搜索目标字段',
    data:function(){ return rows; },
    cols:[
      {t:'目标字段', k:'k', render:function(r){ return '<span class="mono"><b>'+r.k+'</b></span>'+(r.demo?' <span class="tag tag-orange" style="height:16px;font-size:10px">演示</span>':''); }},
      {t:'上游字段', render:function(r){ return r.ups.map(function(u){ return '<div class="mono" style="font-size:11.5px">'+u.from+'</div>'; }).join(''); }},
      {t:'加工逻辑', render:function(r){ return r.ups.map(function(u){ return '<div style="font-size:11.5px;color:var(--text-2)">'+UI.esc(u.transform)+'</div>'; }).join(''); }}
    ],
    ops:function(r){ return '<a onclick="A.linFDetail(\''+r.k+'\')">链路</a>'; }});
};
A._linWalkNode = function(n){
  var t = DB.metaTables.filter(function(x){return x.name===n.id;})[0];
  var ups = DB.tableLineage.filter(function(l){return l.to===n.id;});
  var downs = DB.tableLineage.filter(function(l){return l.from===n.id;});
  UI.modal({title:'血缘节点 - '+n.id, w:'w-md',
    footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>'+(t? '<button class="btn btn-primary" onclick="UI.closeModal();A.metaDetail(\''+t.id+'\')">资产详情</button>':''),
    body: UI.desc([['分层', tag(n.type.split(' ')[0], 'blue')], ['主题域', t? t.domain:'-'], ['负责人', t? t.owner:'-'],
      ['转换与组装逻辑', '<span style="font-size:11.5px">'+UI.esc(n.summary)+'</span>'],
      ['上游（'+ups.length+'）', ups.map(function(u){ return '<span class="mono">'+u.from+'</span>（'+u.task+'）'; }).join('；')||'无'],
      ['下游（'+downs.length+'）', downs.map(function(x){ return '<span class="mono">'+x.to+'</span>（'+x.task+'）'; }).join('；')||'无']])
    + '<div style="display:flex;gap:8px;margin-top:10px"><button class="btn" onclick="A.linImpact()">影响分析</button><button class="btn" onclick="App.go(\'#/ide\')">IDE查询</button></div>'});
};
App.reg('#/meta/lineage', '血缘分析', function(){
  var html = UI.pageHead('血缘分析',
    '基于操作元数据自动构建表级/字段级血缘：变更影响分析 · 断链检测 · 与DAG任务联动追溯',
    '<button class="btn" onclick="A.linMode(\'table\')">表级血缘</button>'
    +'<button class="btn" onclick="A.linMode(\'field\')">字段级血缘</button>'
    +'<button class="btn btn-primary" onclick="A.linImpact()">影响分析</button>');
  html += '<div class="card no-head"><div class="card-body" style="padding:11px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap">'
    + '<b style="font-size:13px">分析口径</b><span id="linScopeBar">'+A._linScopeSeg()+'</span>'
    + '<span id="linScopeTip" style="font-size:11.5px;color:var(--text-3)">'+({flow:'上栏任务流图定位加工环节，下栏查看该流产出表的血缘走向', table:'按表分析：下栏高亮所选表的直接上游/下游', field:'按字段分析：下栏展示字段级映射清单'}[A._linScope]||'')+'</span>'
    + '</div></div>';
  html += UI.card('任务流图示例',
    '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">'
    + '<span style="font-size:12px;color:var(--text-3)">选择工作流</span>'
    + '<select class="sel" style="width:auto" id="linWfSel" onchange="A.linWfChange()">'
    + DB.workflows.map(function(w){ return '<option value="'+w.id+'"'+(w.id===A._linWf?' selected':'')+'>'+w.id+' '+UI.esc(w.name)+(w.status==='draft'?'（草稿）':'')+'</option>'; }).join('')
    + '</select><span id="linFlowStats" style="margin-left:auto;font-size:11.5px;color:var(--text-3)"></span></div>'
    + '<div id="linFlowMount"></div>');
  html += UI.card('血缘走向', '<div id="linWalkHead"></div><div id="linWalkBody"></div>');
  var tabs = UI.tabs('linTab', [{label:'血缘全景图', render:1},{label:'字段级血缘', render:1},{label:'影响分析', render:1},{label:'断链检测', render:1}], 0);
  html += '<div class="card no-head" style="margin-top:16px"><div class="card-body">'+tabs+'<div id="linTabBody"></div></div></div>';
  App.onAfterRender(function(mm){ if(mm.path.indexOf('#/meta/lineage')===0){ A._linFlowRender(); A._linWalkRender(); A._linTab(0); } });
  UI._tabCb['linTab'] = A._linTab;
  return html;
});
A._linTab = function(i){
  var b = document.getElementById('linTabBody');
  if(i===0){
    var layerY = {}; var seq = {};
    var nodes = DB.lineageGraph.nodes.map(function(n){
      seq[n.layer] = (seq[n.layer]||0)+1;
      return {id:n.id, layer:n.layer, x:LAYERX[n.layer]||40, y:20+(seq[n.layer]-1)*78, w:180, h:52};
    });
    var maxH = Math.max.apply(null, nodes.map(function(n){return n.y+80;}));
    var svg = '<svg class="dag-svg" width="1080" height="'+maxH+'" viewBox="0 0 1080 '+maxH+'"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#a8b6cc"/></marker></defs>';
    ['ODS','DIM','DWD','DWS','ADS'].forEach(function(l){
      svg += '<text x="'+(LAYERX[l]+90)+'" y="8" font-size="11" fill="#8c94a6" text-anchor="middle" font-weight="600">'+l+'</text>';
    });
    DB.lineageGraph.edges.forEach(function(e){
      var f = nodes.find(function(n){return n.id===e[0];}), t = nodes.find(function(n){return n.id===e[1];});
      if(!f||!t) return;
      var x1=f.x+f.w, y1=f.y+f.h/2, x2=t.x, y2=t.y+t.h/2, mx=(x1+x2)/2;
      svg += '<path class="dag-edge" d="M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2+'"/>';
    });
    nodes.forEach(function(n){
      var lc = n.layer==='ODS'?'#0891b2':n.layer==='DWD'?'#1668dc':n.layer==='DWS'?'#7c3aed':n.layer==='ADS'?'#16a34a':'#d97706';
      svg += '<g class="dag-node" onclick="A.linNode(\''+n.id+'\')">'
        +'<rect class="n-box" x="'+n.x+'" y="'+n.y+'" width="'+n.w+'" height="'+n.h+'" rx="8"/>'
        +'<rect x="'+n.x+'" y="'+n.y+'" width="4" height="'+n.h+'" rx="2" fill="'+lc+'"/>'
        +'<text x="'+(n.x+14)+'" y="'+(n.y+22)+'" font-size="11.5" font-weight="600" fill="#242938">'+n.id+'</text>'
        +'<text x="'+(n.x+14)+'" y="'+(n.y+40)+'" font-size="10" fill="#8c94a6">'+n.layer+' · 点击查看</text></g>';
    });
    svg += '</svg>';
    b.innerHTML = '<div class="dag-legend"><span><i class="lg-dot" style="background:#a8b6cc;display:inline-block;width:16px;height:2px;vertical-align:middle"></i> 依赖关系</span>'
      +'<span style="margin-left:auto">节点数 '+nodes.length+' · 关系数 '+DB.lineageGraph.edges.length+' · 点击节点查看上下游与产出任务</span></div>'
      +'<div class="dag-wrap" style="overflow:auto">'+svg+'</div><div id="linNodeBox" style="margin-top:14px"></div>';
  }
  if(i===1){
    b.innerHTML = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>字段级血缘由 ETL 表达式算子与 SQL 解析自动生成，选择目标字段查看其上游加工链路。</span></div>'
      + UI.tbl({id:'t_linf', rowKey:'k', pageSize:8, searchKeys:['k'], data:function(){
          return Object.keys(DB.fieldLineage).map(function(k){return {k:k, ups:DB.fieldLineage[k]};});},
        cols:[{t:'目标字段', k:'k', render:function(r){return '<span class="mono"><b>'+r.k+'</b></span>';}},
              {t:'上游字段', render:function(r){return r.ups.map(function(u){return '<div class="mono" style="font-size:11.5px">'+u.from+'</div>';}).join('');}},
              {t:'加工逻辑', render:function(r){return r.ups.map(function(u){return '<div style="font-size:11.5px;color:var(--text-2)">'+UI.esc(u.transform)+'</div>';}).join('');}}],
        ops:function(r){return '<a onclick="A.linFDetail(\''+r.k+'\')">链路详情</a>';}});
  }
  if(i===2){
    var im = DB.impactExample;
    b.innerHTML = '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>影响分析：若变更 <b class="mono">'+im.table+'</b> 的结构/口径，以下下游将受影响，请按「通知负责人 → 调整下游 → 重跑验证」闭环处理。</span></div>'
      + '<div class="grid" style="grid-template-columns:1fr 1fr;gap:14px">'
      + UI.card('受影响下游表（'+im.downTables.length+'）', im.downTables.map(function(t){return '<div class="checker-line"><span>▤</span><b class="mono">'+t.name+'</b><span style="margin-left:auto;color:var(--text-3)">'+t.task+'</span></div>';}).join(''))
      + UI.card('受影响任务/工作流（'+im.downTasks.length+'）', im.downTasks.map(function(t){return '<div class="checker-line"><span>⑃</span><b>'+t.name+'</b><span style="margin-left:auto;color:var(--text-3)">'+t.wf+'</span></div>';}).join(''))
      + UI.card('受影响指标（'+im.downIndicators.length+'）', im.downIndicators.map(function(t){return '<div class="checker-line"><span>✦</span><b>'+t.name+'</b><span style="margin-left:auto;color:var(--text-3)">'+t.code+'</span></div>';}).join(''))
      + UI.card('受影响报表', im.reports.map(function(r){return '<div class="checker-line"><span>◫</span><b>'+r+'</b></div>';}).join(''))
      + '</div>';
  }
  if(i===3){
    b.innerHTML = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>断链检测：扫描血缘图中「有产出任务但上游未入工作流」或「表无产出任务」的异常链路。</span></div>'
      + '<div class="checker-line warn" style="border-color:#f3ddb0;background:#fffbf2"><span>⚠</span><div><b>dwd_gl_voucher_detail</b> 上游产出任务 ETL004 未纳入任何工作流调度<div style="font-size:11px;color:var(--text-3)">建议：创建「财务凭证入仓」工作流并发布上线（已在 DAG 模块提供草稿 WF004）</div><div style="margin-top:6px"><button class="btn btn-sm" onclick="App.go(\'#/dag/list\')">去处理</button></div></div></div>'
      + '<div class="checker-line warn" style="border-color:#f3ddb0;background:#fffbf2"><span>⚠</span><div><b>dim_product</b> 无产出任务记录（引用自 ETL006，未注册到平台）<div style="font-size:11px;color:var(--text-3)">建议：在 ETL 任务中注册 etl_dim_product_sync 并纳入维度日更工作流</div><div style="margin-top:6px"><button class="btn btn-sm" onclick="App.go(\'#/etl/list\')">去注册</button></div></div></div>'
      + '<div class="checker-line ok"><span>✓</span><div><b>其余 8 张表</b> 血缘链路完整，均有任务与工作流承接</div></div>';
  }
};
A.linNode = function(name){
  var t = DB.metaTables.find(function(x){return x.name===name;});
  var ups = DB.tableLineage.filter(function(l){return l.to===name;});
  var downs = DB.tableLineage.filter(function(l){return l.from===name;});
  document.getElementById('linNodeBox').innerHTML = UI.card('血缘详情 - '+name,
    UI.desc([['分层', t? tag(t.layer,'blue') : '-'], ['主题域', t? t.domain:'-'], ['负责人', t? t.owner:'-'],
      ['上游（'+ups.length+'）', ups.map(function(u){return '<span class="mono">'+u.from+'</span>（'+u.task+'）';}).join('；')||'无'],
      ['下游（'+downs.length+'）', downs.map(function(d){return '<span class="mono">'+d.to+'</span>（'+d.task+'）';}).join('；')||'无']])
    + '<div style="display:flex;gap:8px;margin-top:10px">'
    + (t? '<button class="btn" onclick="A.metaDetail(\''+t.id+'\')">资产详情</button>':'')
    + '<button class="btn" onclick="A.linImpact()">影响分析</button><button class="btn" onclick="App.go(\'#/ide\')">IDE查询</button></div>');
};
A.linFDetail = function(k){
  var ups = DB.fieldLineage[k]||[];
  UI.modal({title:'字段血缘链路 - '+k, w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.timeline(ups.map(function(u){return {title:'上游 <span class="mono">'+u.from+'</span>', body:UI.esc(u.transform)};}).concat([{title:'目标 <span class="mono">'+k+'</span>', cls:'ok', body:'字段级血缘终点'}]))});
};
A.linMode = A.linImpact = function(){ UI._tabCb['linTab'] && (document.querySelectorAll('#linTab .tab')[2].click()); };

/* ---- 数据资产地图（总概览默认 + 按分层/分域/大类归类） ---- */
A._mapViewCur = 'overview';
A._MAP_LAYERS = ['ODS','DIM','DWD','DWS','ADS'];
A._MAP_LAYER_C = {ODS:'#0891b2', DIM:'#d97706', DWD:'#1668dc', DWS:'#7c3aed', ADS:'#16a34a'};
App.reg('#/meta/map', '数据资产地图', function(){
  var totalRows = DB.metaTables.reduce(function(s,t){return s+t.rows;},0);
  var html = UI.pageHead('数据资产地图',
    '多维归类浏览数据资产：总概览矩阵 / 按分层 / 按业务域 / 按大类 · 与元数据目录联动',
    '<button class="btn" onclick="App.go(\'#/meta/catalog\')">前往元数据目录</button>');
  html += '<div class="card no-head"><div class="card-body" style="padding:11px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap">'
    + '<span id="mapSegBar">'+A._mapSeg()+'</span>'
    + '<span style="margin-left:auto;font-size:11.5px;color:var(--text-3)">'+DB.bizDomains.length+' 个业务域 · '+A._MAP_LAYERS.length+' 个分层 · '+DB.metaTables.length+' 张表 · 共 '+fmt(totalRows)+' 行</span>'
    + '</div></div>';
  html += '<div id="mapViewBody">'+A._mapView()+'</div>';
  return html;
});
A._mapSeg = function(){
  var defs = [['overview','总概览'],['layer','按分层'],['domain','按业务域'],['category','按大类']];
  return '<div style="display:inline-flex;border:1px solid var(--border);border-radius:8px;overflow:hidden;vertical-align:middle">'
    + defs.map(function(x){
      var on = A._mapViewCur===x[0];
      return '<span onclick="A.mapView(\''+x[0]+'\')" style="padding:6px 18px;font-size:12.5px;cursor:pointer;user-select:none;'+(on?'background:var(--primary);color:#fff;font-weight:600':'background:#fff;color:var(--text-2)')+'">'+x[1]+'</span>';
    }).join('') + '</div>';
};
A.mapView = function(v){
  A._mapViewCur = v;
  var bar = document.getElementById('mapSegBar'); if(bar) bar.innerHTML = A._mapSeg();
  var body = document.getElementById('mapViewBody'); if(body) body.innerHTML = A._mapView();
};
A._mapView = function(){
  var v = A._mapViewCur||'overview';
  if(v==='layer') return A._mapLayer();
  if(v==='domain') return A._mapDomain();
  if(v==='category') return A._mapCategory();
  return A._mapOverview();
};
A._mapStatBar = function(items){
  return '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">'
    + items.map(function(x){ return '<div class="stat-card" style="flex:1;min-width:118px;padding:10px"><div><div class="stat-num" style="font-size:18px">'+x[1]+'</div><div class="stat-label">'+x[0]+'</div></div></div>'; }).join('') + '</div>';
};
A._mapCard = function(name, extra){
  return '<div class="checker-line" onclick="App.go(\'#/meta/catalog\')" style="cursor:pointer;margin-bottom:7px"><span>▤</span><span class="mono" style="flex:1;font-size:11.5px">'+name+'</span>'
    + (extra? '<span style="font-size:10.5px;color:var(--text-3);white-space:nowrap">'+extra+'</span>':'') + '</div>';
};
A._mapOverview = function(){
  var doms = DB.bizDomains;
  var totalRows = DB.metaTables.reduce(function(s,t){return s+t.rows;},0);
  var covLayers = A._MAP_LAYERS.filter(function(l){ return DB.metaTables.some(function(t){return t.layer===l;}); }).length;
  var covDomains = doms.filter(function(d){ return DB.metaTables.some(function(t){return t.domain===d.name;}); }).length;
  var tbl = '<div class="table-wrap"><table class="tbl"><thead><tr><th>分层 ＼ 业务域</th>'
    + doms.map(function(d){ return '<th style="text-align:center"><span style="display:inline-block;width:8px;height:8px;border-radius:3px;background:'+d.color+';margin-right:5px"></span>'+d.name+'</th>'; }).join('')
    + '<th style="text-align:center">小计</th></tr></thead><tbody>';
  A._MAP_LAYERS.forEach(function(l){
    var rowCnt = 0;
    tbl += '<tr><td><b>'+l+'</b></td>';
    doms.forEach(function(d){
      var c = DB.metaTables.filter(function(t){return t.layer===l && t.domain===d.name;}).length;
      rowCnt += c;
      tbl += '<td style="text-align:center;'+(c>0?'background:#eef4ff':'')+'">'+(c>0? '<b style="color:var(--primary)">'+c+'</b>' : '<span style="color:var(--border-strong)">·</span>')+'</td>';
    });
    tbl += '<td style="text-align:center"><b>'+rowCnt+'</b></td></tr>';
  });
  tbl += '<tr><td><b>合计</b></td>'
    + doms.map(function(d){ return '<td style="text-align:center"><b>'+DB.metaTables.filter(function(t){return t.domain===d.name;}).length+'</b></td>'; }).join('')
    + '<td style="text-align:center"><b>'+DB.metaTables.length+'</b></td></tr></tbody></table></div>';
  return '<div class="dag-legend">矩阵口径：行=分层（ODS 接入 → DIM/DWD 加工 → DWS 汇总 → ADS 应用） · 列=业务域 · 格内数字=已纳管表数</div>'
    + '<div class="card-body" style="padding:14px 16px">'
    + A._mapStatBar([['已纳管表', DB.metaTables.length], ['覆盖分层', covLayers+' / '+A._MAP_LAYERS.length], ['覆盖业务域', covDomains+' / '+doms.length], ['总行数', fmt(totalRows)]])
    + tbl
    + '<div class="lock-tip">统计取自元数据目录（DB.metaTables）按 layer × bizDomain 聚合；切换上方分段控件可按分层 / 业务域 / 大类归类浏览。</div></div>';
};
A._mapLayer = function(){
  var cols = A._MAP_LAYERS.map(function(l){
    var ts = DB.metaTables.filter(function(t){return t.layer===l;});
    return '<div style="flex:1;min-width:198px;background:var(--bg);border:1px solid var(--border);border-radius:9px;padding:10px">'
      + '<div style="display:flex;align-items:center;gap:7px;margin-bottom:9px"><span class="tag" style="background:'+A._MAP_LAYER_C[l]+'18;color:'+A._MAP_LAYER_C[l]+';font-weight:600">'+l+'</span>'
      + '<span style="margin-left:auto;font-size:11px;color:var(--text-3)">'+ts.length+' 张</span></div>'
      + (ts.length? ts.map(function(t){ return A._mapCard(t.name, fmt(t.rows)+' 行'); }).join('') : '<div class="empty" style="padding:10px"><p>暂无</p></div>')
      + '</div>';
  }).join('');
  return '<div class="dag-legend">按数据分层归类 · 每列一个分层（ODS/DIM/DWD/DWS/ADS） · 表资产卡点击进入元数据目录</div>'
    + '<div class="card-body" style="padding:14px 16px">'
    + A._mapStatBar(A._MAP_LAYERS.map(function(l){ return [l+' 表', DB.metaTables.filter(function(t){return t.layer===l;}).length]; }))
    + '<div style="display:flex;gap:12px;align-items:stretch;overflow:auto">'+cols+'</div>'
    + '<div class="lock-tip">各层语义：ODS 原样接入 · DIM 公共维度 · DWD 明细加工 · DWS 轻度汇总 · ADS 应用宽表。</div></div>';
};
A._mapDomain = function(){
  var doms = DB.bizDomains.filter(function(d){ return DB.metaTables.some(function(t){return t.domain===d.name;}); });
  var cols = doms.map(function(d){
    var ts = DB.metaTables.filter(function(t){return t.domain===d.name;});
    return '<div style="flex:1;min-width:216px;background:var(--bg);border:1px solid var(--border);border-radius:9px;padding:10px">'
      + '<div style="display:flex;align-items:center;gap:7px;margin-bottom:5px"><span style="display:inline-block;width:9px;height:9px;border-radius:3px;background:'+d.color+'"></span><b style="font-size:12.5px">'+d.name+'</b>'
      + '<span style="margin-left:auto;font-size:11px;color:var(--text-3)">'+ts.length+' 张</span></div>'
      + '<div style="font-size:10.5px;color:var(--text-3);margin-bottom:9px">'+UI.esc(d.desc)+'</div>'
      + ts.map(function(t){ return A._mapCard(t.name, t.layer); }).join('')
      + '</div>';
  }).join('');
  return '<div class="dag-legend">按业务域归类 · 交易/经营/商品/财务/公共等分组列 · 表资产卡点击进入元数据目录</div>'
    + '<div class="card-body" style="padding:14px 16px">'
    + A._mapStatBar(doms.map(function(d){ return [d.name, DB.metaTables.filter(function(t){return t.domain===d.name;}).length]; }))
    + '<div style="display:flex;gap:12px;align-items:stretch;overflow:auto">'+cols+'</div>'
    + '<div class="lock-tip">业务域由主题域标签自动归类（采集时按命名规则映射），可在目录中调整表的主题域归属。</div></div>';
};
A._mapCategory = function(){
  var reportDemo = ['经营日报','支付渠道分析','运营周报','用户活跃分析'];
  var cats = [
    {name:'数据表', icon:'▤', color:'#1668dc', cnt:DB.metaTables.length, unit:'张', link:'#/meta/catalog', linkTxt:'进入元数据目录',
     items:DB.metaTables.map(function(t){return t.name;}).slice(0,5)},
    {name:'指标', icon:'✦', color:'#7c3aed', cnt:DB.indicators.length, unit:'项', link:'#/ind/list', linkTxt:'指标目录',
     items:DB.indicators.slice(0,5).map(function(i){return i.name+'（'+i.id+'）';})},
    {name:'标准', icon:'§', color:'#16a34a', cnt:DB.stdElements.length + DB.stdCodes.length, unit:'项', link:'#/std/element', linkTxt:'标准管理',
     items:DB.stdElements.slice(0,3).map(function(s){return s.cn+' '+s.en;}).concat(DB.stdCodes.slice(0,2).map(function(c){return c.name+'（'+c.id+'）';}))},
    {name:'报告', icon:'◫', color:'#d97706', cnt:reportDemo.length, unit:'份', link:'', linkTxt:'', items:reportDemo}
  ];
  return '<div class="dag-legend">按资产大类归类：数据表 / 指标 / 标准 / 报告 · 每类卡片列出纳管样本与入口链接</div>'
    + '<div class="card-body" style="padding:14px 16px">'
    + A._mapStatBar(cats.map(function(c){ return [c.name, c.cnt+' '+c.unit]; }))
    + '<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">'
    + cats.map(function(c){
      return '<div class="card" style="margin:0"><div class="card-head"><h3><span style="display:inline-block;width:9px;height:9px;border-radius:3px;background:'+c.color+';margin-right:7px"></span>'+c.name+'</h3>'
        + '<div class="ch-acts"><span class="tag" style="background:'+c.color+'18;color:'+c.color+'">'+c.cnt+' '+c.unit+'</span></div></div><div class="card-body">'
        + c.items.map(function(it){ return '<div class="checker-line" style="margin-bottom:7px"><span>'+c.icon+'</span><span class="mono" style="flex:1;font-size:11.5px">'+UI.esc(it)+'</span></div>'; }).join('')
        + (c.link? '<button class="btn btn-sm" style="margin-top:4px" onclick="App.go(\''+c.link+'\')">'+c.linkTxt+' →</button>':'')
        + '</div></div>';
    }).join('') + '</div>'
    + '<div class="lock-tip">报告类为演示数据：正式报告资产将在 BI/报表模块纳管后自动归入；指标/标准数量来自指标管理（M10）与数据标准（M10）登记。</div></div>';
};

/* ---- 标签管理 ---- */
App.reg('#/meta/tag', '标签管理', function(){
  var html = UI.pageHead('标签管理',
    '面向资产的分类标签体系：重要性 / 用途 / 标准 / 安全 / 质量五类，支持批量打标与目录联动',
    '<button class="btn btn-primary" onclick="A.mtCreate()">+ 新建标签</button>');
  html += UI.card('标签列表', UI.tbl({
    id:'t_mtag', rowKey:'id', pageSize:8, searchKeys:['name','cat','desc'], searchPh:'搜索标签',
    filters:[{k:'cat', label:'分类', options:[{v:'重要性',t:'重要性'},{v:'用途',t:'用途'},{v:'标准',t:'标准'},{v:'安全',t:'安全'},{v:'质量',t:'质量'}]}],
    data:function(){ return DB.metaTags; },
    cols:[
      {t:'标签', k:'name', render:function(r){return '<span class="tag" style="background:'+r.color+'22;color:'+r.color+';font-weight:600">'+r.name+'</span>';}},
      {t:'分类', k:'cat', render:function(r){return tag(r.cat,'blue');}},
      {t:'描述', k:'desc'},
      {t:'已打标表', render:function(r){return '<a onclick="A.mtTables(\''+r.id+'\')"><b>'+r.tables.length+'</b> 张</a>';}}
    ],
    ops:function(r){
      return '<a onclick="A.mtTables(\''+r.id+'\')">打标资产</a>'
        +'<a onclick="A.mtEdit(\''+r.id+'\')">编辑</a>'
        +'<a class="danger" onclick="UI.delRow(DB.metaTags, \'id\', \''+r.id+'\', \''+r.name+'\')">删除</a>';
    }}));
  return html;
});
A.mtFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('标签名称', 'mt_name', {value:d.name, req:true})
    + UI.fSelect('标签分类', 'mt_cat', ['重要性','用途','标准','安全','质量'], {value:d.cat||'重要性'})
    + UI.fInput('颜色', 'mt_color', {value:d.color||'#1668dc', type:'color'})
    + UI.fTextarea('描述', 'mt_desc', {value:d.desc, rows:2})
    + '</div>';
};
A.mtCreate = function(){
  UI.drawer({title:'新建标签', body:A.mtFormFields({}), onOk:function(){
    var name = UI.val('mt_name');
    if(!name){ UI.toast('请填写标签名称', 'warn'); return false; }
    DB.metaTags.push({id:'TG'+String(DB.metaTags.length+1).padStart(2,'0'), name:name, cat:UI.val('mt_cat'), color:UI.val('mt_color'), cnt:0, desc:UI.val('mt_desc'), tables:[]});
    UI.toast('标签「'+name+'」已创建', 'success');
  }});
};
A.mtEdit = function(id){
  var d = DB.metaTags.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑标签 - '+d.name, body:A.mtFormFields(d), onOk:function(){
    Object.assign(d, {name:UI.val('mt_name'), cat:UI.val('mt_cat'), color:UI.val('mt_color'), desc:UI.val('mt_desc')});
    UI.toast('标签已保存', 'success');
  }});
};
A.mtTables = function(id){
  var d = DB.metaTags.find(function(x){return x.id===id;});
  UI.drawer({title:'为标签「'+d.name+'」选择资产', w:'w-md', body:
    DB.metaTables.map(function(t){
      return '<label style="display:flex;gap:8px;align-items:center;padding:7px 10px;border:1px solid var(--border);border-radius:7px;margin-bottom:7px;cursor:pointer"><input type="checkbox" class="mt-tbl" value="'+t.id+'" '+(d.tables.indexOf(t.id)>=0?'checked':'')+'><span class="mono" style="font-size:12px">'+t.name+'</span><span style="margin-left:auto;font-size:11px;color:var(--text-3)">'+t.domain+' · '+t.layer+'</span></label>';
    }).join(''),
    onOk:function(){
      var vals = Array.prototype.map.call(document.querySelectorAll('.mt-tbl:checked'), function(e){return e.value;});
      d.tables = vals; d.cnt = vals.length;
      DB.metaTables.forEach(function(t){ t.tags = (t.tags||[]).filter(function(x){return x!==d.name;}); if(vals.indexOf(t.id)>=0) t.tags.push(d.name); });
      UI.toast('标签「'+d.name+'」已关联 '+vals.length+' 张表', 'success');
    }});
};
})();
