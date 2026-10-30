/* ============================================================
   M07 数据质量（评分卡/规则/检查任务/异常核查/报告/告警）
   业务闭环：规则 → 检查任务(调度/ETL联动) → 检查结果 → 异常核查(修复/忽略) → 报告 → 告警
   ============================================================ */
(function(){
/* ---- 质量评分卡 ---- */
App.reg('#/qc/score', '质量评分卡', function(){
  var last = DB.qcReports[0];
  var html = UI.pageHead('质量评分卡',
    '全库质量健康度总览：六维得分 · 分层趋势 · 问题分布，评分 = 100 - Σ(问题扣分)，弱规则半权计分',
    '<button class="btn btn-primary" onclick="App.go(\'#/qc/task\')">检查任务</button>'
    +'<button class="btn" onclick="App.go(\'#/qc/report\')">质量报告</button>');
  html += '<div class="grid grid-4" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+last.score+'</div><div class="stat-label">综合评分（'+last.period+'）</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#e5484d">⚑</span><div><div class="stat-num">'+DB.qcExceptions.filter(function(e){return e.status==='pending';}).length+'</div><div class="stat-label">待核查异常</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#1668dc">⌇</span><div><div class="stat-num">'+DB.qcRules.filter(function(r){return r.status==='enabled';}).length+'</div><div class="stat-label">生效规则（强 '+DB.qcRules.filter(function(r){return r.level==='强规则' && r.status==='enabled';}).length+'）</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#d97706">⏱</span><div><div class="stat-num">100</div><div class="stat-label">及时性得分（SLA达标）</div></div></div></div>';
  html += '<div class="grid" style="grid-template-columns:1.6fr 1fr;gap:16px;align-items:flex-start">'
    + UI.card('分层质量评分趋势（近8日）', Charts.line({labels:DB.qcScoreTrend.labels, series:[
        {name:'ODS', color:'#0891b2', data:DB.qcScoreTrend.ods},{name:'DWD', color:'#1668dc', data:DB.qcScoreTrend.dwd},
        {name:'DWS', color:'#7c3aed', data:DB.qcScoreTrend.dws},{name:'ADS', color:'#16a34a', data:DB.qcScoreTrend.ads}]})
      + '<div class="lock-tip">DWD 层 09-11 降至 90 分：QC-R-012 支付金额范围检查失败（12 行异常），点击下方异常核查处理。</div>')
    + UI.card('六维雷达得分', '<div class="grid grid-2" style="gap:10px">'
      + DB.qcDimScore.map(function(d){
        return '<div style="display:flex;gap:10px;align-items:center;padding:9px 11px;border:1px solid var(--border);border-radius:9px">'+Charts.ring(d.score, 56)+'<div><b style="font-size:12.5px">'+d.name+'</b><div style="font-size:11px;color:var(--text-3)">'+(d.score>=95?'优':d.score>=90?'良':'待改进')+'</div></div></div>';
      }).join('')+'</div>')
    +'</div>';
  html += UI.card('异常明细（待处理 '+DB.qcExceptions.filter(function(e){return e.status==='pending';}).length+'）',
    UI.tbl({id:'t_qcse', rowKey:'id', pageSize:5, searchKeys:['ruleName','table'], data:function(){return DB.qcExceptions;},
      cols:[{t:'异常单', k:'id'},{t:'规则', k:'ruleName'},{t:'表', k:'table', render:function(r){return '<span class="mono">'+r.table+'</span>';}},
            {t:'异常数', k:'cnt'},{t:'日期', k:'dt'},{t:'状态', k:'status', render:function(r){return st(r.status);}}],
      ops:function(r){return '<a onclick="App.go(\'#/qc/exception\')">核查</a>';}}));
  return A.qcTabs('score') + '<div id="qcTabMain">'+html+'</div>' + A.qfFlowPanel();
});

/* ---- 质量规则 ---- */
App.reg('#/qc/rule', '质量规则', function(){
  var html = UI.pageHead('质量规则',
    '六维规则模板建规则：完整性/准确性/一致性/及时性/唯一性/有效性；强规则失败阻断下游，弱规则告警不阻断',
    '<button class="btn btn-primary" onclick="A.qrCreate()">+ 新建规则</button>'
    +'<button class="btn" onclick="A.qrTemplates()">从模板创建</button>');
  var dims = {};
  DB.qcDims.forEach(function(d){ dims[d.code]=d; });
  html += '<div class="grid grid-6" style="grid-template-columns:repeat(6,1fr);margin-bottom:16px">'
    + DB.qcDims.map(function(d){
      var cnt = DB.qcRules.filter(function(r){return r.dim===d.code;}).length;
      return '<div class="stat-card hoverable" onclick="UI._tf(\'t_qr\',\'dim\',\''+d.code+'\')"><span class="type-icon" style="background:'+d.color+'">'+d.icon+'</span><div><div class="stat-num">'+cnt+'</div><div class="stat-label">'+d.name+'</div></div></div>';
    }).join('')+'</div>';
  html += UI.card('规则列表', UI.tbl({
    id:'t_qr', rowKey:'id', pageSize:8, selectable:true, searchKeys:['id','name','table','field'], searchPh:'搜索规则/表/字段',
    filters:[
      {k:'dim', label:'维度', options:DB.qcDims.map(function(d){return {v:d.code,t:d.name};})},
      {k:'level', label:'级别', options:[{v:'强规则',t:'强规则'},{v:'弱规则',t:'弱规则'}]},
      {k:'status', label:'状态', options:[{v:'enabled',t:'启用'},{v:'disabled',t:'停用'}]},
      {k:'lastResult', label:'最近结果', options:[{v:'pass',t:'通过'},{v:'fail',t:'失败'}]}
    ],
    data:function(){ return DB.qcRules; },
    cols:[
      {t:'规则', k:'name', render:function(r){
        var d = dims[r.dim]||{};
        return '<div><a onclick="A.qrDetail(\''+r.id+'\')"><b>'+r.name+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+d.name+' · '+r.type+'</div></div>';}},
      {t:'检核对象', render:function(r){return '<span class="mono" style="font-size:11.5px">'+r.table+(r.field&&r.field!=='-'?'.'+r.field:'')+'</span>';}},
      {t:'阈值', k:'threshold', render:function(r){return '<span style="font-size:11.5px">'+UI.esc(r.threshold)+'</span>';}},
      {t:'级别', k:'level', render:function(r){return tag(r.level, r.level==='强规则'?'red':'orange');}},
      {t:'最近结果', render:function(r){return st(r.lastResult);}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}},
      {t:'负责人', k:'owner'}
    ],
    ops:function(r){
      return '<a onclick="A.qrDetail(\''+r.id+'\')">详情</a>'
        +'<a onclick="A.qrTest(\''+r.id+'\')">试跑</a>'
        +'<a onclick="A.qrEdit(\''+r.id+'\')">编辑</a>'
        +'<a onclick="UI.toggleStatus(DB.qcRules.find(function(x){return x.id===\''+r.id+'\'}))">'+(r.status==='enabled'?'停用':'启用')+'</a>'
        +'<a class="danger" onclick="A.qrDel(\''+r.id+'\')">删除</a>';
    }}));
  return html;
});
A.qrTemplates = function(){
  UI.modal({title:'规则模板库（六维）', w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    '<div class="grid" style="grid-template-columns:repeat(3,1fr)">'
    + [['空值检查','COMPLETENESS','字段空值率 ≤ 阈值'],['行数波动','COMPLETENESS','日环比波动 ≤ ±30%'],['记录数比对','COMPLETENESS','与源表行数差 = 0'],
       ['范围检查','ACCURACY','值域 [min, max]'],['业务规则','ACCURACY','SQL表达式校验'],['精度比对','ACCURACY','与源聚合值差 ≤ ε'],
       ['跨表一致性','CONSISTENCY','两表聚合差 ≤ ε'],['枚举值比对','CONSISTENCY','值域集合一致'],['SLA检查','TIMELINESS','DDL 时间内产出'],
       ['主键唯一','UNIQUENESS','重复数 = 0'],['联合唯一','UNIQUENESS','组合键重复 = 0'],['格式正则','VALIDITY','匹配 ^regex$'],
       ['枚举检查','VALIDITY','值域 ∈ {…}'],['长度检查','VALIDITY','长度 ≤ max'],['引用完整性','VALIDITY','外键值存在于维表']]
      .map(function(t){ var d = DB.qcDims.find(function(x){return x.code===t[1];});
        return '<div class="stat-card hoverable" onclick="A.qrFromTpl(\''+t[0]+'\',\''+t[1]+'\')"><span class="type-icon" style="background:'+d.color+'">'+d.icon+'</span><div><b style="font-size:12.5px">'+t[0]+'</b><div style="font-size:11px;color:var(--text-3)">'+UI.esc(t[2])+'</div></div></div>';
      }).join('')+'</div>'});
};
A.qrFromTpl = function(tpl, dim){
  UI.closeModal();
  UI.drawer({title:'从模板创建 - '+tpl, w:'w-lg', body:
    UI.fInput('规则名称', 'qt_name', {value:DB.metaTables[0].name+' '+tpl, req:true})
    + UI.fSelect('检核表', 'qt_table', DB.metaTables.map(function(t){return {v:t.name,t:t.name};}), {})
    + UI.fInput('检核字段（及时性/行数类可留空）', 'qt_field', {})
    + UI.fSelect('维度', 'qt_dim', DB.qcDims.map(function(d){return {v:d.code,t:d.name};}), {value:dim})
    + UI.fInput('阈值', 'qt_threshold', {req:true, ph:'如：空值率 ≤ 1%'})
    + UI.fRadio('规则级别', 'qt_level', [{v:'强规则',t:'强规则（失败阻断下游）'},{v:'弱规则',t:'弱规则（告警不阻断）'}], '强规则'),
    onOk:function(){
      var name = UI.val('qt_name');
      if(!name||!UI.val('qt_threshold')){ UI.toast('请填写规则名称与阈值', 'warn'); return false; }
      DB.qcRules.push({id:'QC-R-0'+(40+DB.qcRules.length), name:name, table:UI.val('qt_table'), field:UI.val('qt_field')||'-', dim:UI.val('qt_dim'), type:tpl, threshold:UI.val('qt_threshold'), level:UI.radioVal('qt_level','强规则'), status:'enabled', owner:DB.user.name, lastResult:'pass', linkTask:'-'});
      UI.toast('规则已创建并启用，可在检查任务中编排调度', 'success');
    }});
};
A.qrFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('规则名称', 'qr_name', {value:d.name, req:true})
    + UI.fSelect('检核表', 'qr_table', DB.metaTables.map(function(t){return {v:t.name,t:t.name};}), {value:d.table})
    + UI.fInput('检核字段', 'qr_field', {value:d.field, ph:'-'})
    + UI.fSelect('质量维度', 'qr_dim', DB.qcDims.map(function(x){return {v:x.code,t:x.name};}), {value:d.dim})
    + UI.fInput('检查类型', 'qr_type', {value:d.type})
    + UI.fInput('阈值', 'qr_threshold', {value:d.threshold, req:true})
    + UI.fRadio('规则级别', 'qr_level', [{v:'强规则',t:'强规则'},{v:'弱规则',t:'弱规则'}], d.level||'强规则')
    + '</div>';
};
A.qrCreate = function(){ UI.drawer({title:'新建质量规则', w:'w-lg', body:A.qrFormFields({}), onOk:function(){
  var name = UI.val('qr_name');
  if(!name||!UI.val('qr_threshold')){ UI.toast('请填写规则名称与阈值', 'warn'); return false; }
  DB.qcRules.push({id:'QC-R-0'+(40+DB.qcRules.length), name:name, table:UI.val('qr_table'), field:UI.val('qr_field')||'-', dim:UI.val('qr_dim'), type:UI.val('qr_type')||'自定义', threshold:UI.val('qr_threshold'), level:UI.radioVal('qr_level','强规则'), status:'enabled', owner:DB.user.name, lastResult:'pass', linkTask:'-'});
  UI.toast('规则已创建并启用', 'success');
}}); };
A.qrEdit = function(id){ var d = DB.qcRules.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑规则 - '+d.name, w:'w-lg', body:A.qrFormFields(d), onOk:function(){
    Object.assign(d, {name:UI.val('qr_name'), table:UI.val('qr_table'), field:UI.val('qr_field')||'-', dim:UI.val('qr_dim'), type:UI.val('qr_type'), threshold:UI.val('qr_threshold'), level:UI.radioVal('qr_level','强规则')});
    UI.toast('规则已保存', 'success'); }}); };
A.qrDetail = function(id){
  var d = DB.qcRules.find(function(x){return x.id===id;});
  var dim = DB.qcDims.find(function(x){return x.code===d.dim;})||{};
  UI.modal({title:'规则详情 - '+d.name, w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.desc([['编号', d.id],['维度', (dim.icon||'')+' '+dim.name],['检查类型', d.type],
      ['检核对象','<span class="mono">'+d.table+(d.field&&d.field!=='-'?'.'+d.field:'')+'</span>'],
      ['阈值', d.threshold],['级别', tag(d.level, d.level==='强规则'?'red':'orange')],
      ['状态', st(d.status)],['最近结果', st(d.lastResult)],['联动检查任务', d.linkTask],['负责人', d.owner]])
    + '<div class="lock-tip">强规则失败将阻断 ETL 下游节点并即时告警；弱规则失败仅生成异常单。</div>'});
};
A.qrTest = function(id){
  var d = DB.qcRules.find(function(x){return x.id===id;});
  UI.toast('正在试跑规则「'+d.name+'」...', 'info');
  setTimeout(function(){
    var pass = d.lastResult!=='fail';
    UI.modal({title:'试跑结果 - '+d.name, w:'w-sm', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
      '<div class="checker-line '+(pass?'ok':'err')+'"><span>'+(pass?'✓':'✗')+'</span><b>'+(pass?'校验通过':'校验失败')+'</b><span style="margin-left:auto">'+(pass?'0 行异常':'异常 '+Math.floor(2+Math.random()*10)+' 行')+'</span></div>'
      +'<div class="lock-tip">试跑仅抽样当前分区，不写入结果与异常单；正式检查由检查任务调度执行。</div>'});
  }, 900);
};
A.qrDel = function(id){
  var d = DB.qcRules.find(function(x){return x.id===id;});
  if(d.linkTask && d.linkTask!=='-'){
    UI.confirm({title:'无法删除', danger:true, msg:'规则「'+d.name+'」已被检查任务 '+d.linkTask+' 编排', detail:'请先在检查任务中移除该规则。'});
  } else UI.delRow(DB.qcRules, 'id', id, d.name);
};

/* ---- 检查任务 ---- */
App.reg('#/qc/task', '质量检查任务', function(){
  var html = UI.pageHead('质量检查任务',
    '规则编排执行：支持独立调度与 ETL 前置联动（产出即检核），失败可阻断工作流下游节点',
    '<button class="btn btn-primary" onclick="A.qtCreate()">+ 新建检查任务</button>');
  html += UI.card('检查任务列表', UI.tbl({
    id:'t_qt', rowKey:'id', pageSize:8, searchKeys:['id','name'], searchPh:'搜索任务',
    data:function(){ return DB.qcTasks; },
    cols:[
      {t:'任务', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+'</div>';}},
      {t:'范围', render:function(r){return '表 '+r.tables+' · 规则 '+r.rules;}},
      {t:'调度', k:'cron', render:function(r){return '<span class="mono" style="font-size:11.5px">'+r.cron+'</span>';}},
      {t:'ETL联动', k:'linkEtl'},
      {t:'最近执行', k:'lastRun'},
      {t:'结果', render:function(r){return st(r.lastResult);}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.qtRun(\''+r.id+'\')">立即执行</a>'
        +'<a onclick="A.qtRules(\''+r.id+'\')">编排规则</a>'
        +'<a onclick="A.qtEdit(\''+r.id+'\')">编辑</a>'
        +'<a onclick="UI.toggleStatus(DB.qcTasks.find(function(x){return x.id===\''+r.id+'\'}))">'+(r.status==='enabled'?'停用':'启用')+'</a>'
        +'<a class="danger" onclick="UI.delRow(DB.qcTasks, \'id\', \''+r.id+'\', \''+r.name+'\')">删除</a>';
    }}));
  return A.qcTabs('task') + '<div id="qcTabMain">'+html+'</div>' + A.qfFlowPanel();
});
A.qtFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('任务名称', 'qt2_name', {value:d.name, req:true})
    + UI.fInput('Cron 表达式', 'qt2_cron', {value:d.cron||'0 0 3 * * ?'})
    + UI.fSwitch('ETL 前置联动（产出即检核，失败阻断下游）', 'qt2_link', !!d.linkEtl && d.linkEtl!=='否', '选择后在 ETL 任务中挂载为前置校验节点')
    + '</div>';
};
A.qtCreate = function(){ UI.drawer({title:'新建检查任务', w:'w-lg', body:A.qtFormFields({}), onOk:function(){
  var name = UI.val('qt2_name');
  if(!name){ UI.toast('请填写任务名称', 'warn'); return false; }
  var link = UI.switchOn('qt2_link');
  DB.qcTasks.push({id:'QT00'+(DB.qcTasks.length+1), name:name, tables:0, rules:0, cron:UI.val('qt2_cron'), linkEtl:link?'是（新建联动）':'否', status:'enabled', lastRun:'-', lastResult:'-'});
  UI.toast('检查任务已创建，请编排规则', 'success'); }}); };
A.qtEdit = function(id){ var d = DB.qcTasks.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑检查任务 - '+d.name, w:'w-lg', body:A.qtFormFields(d), onOk:function(){
    d.name = UI.val('qt2_name'); d.cron = UI.val('qt2_cron');
    UI.toast('检查任务已保存', 'success'); }}); };
A.qtRun = function(id){
  var d = DB.qcTasks.find(function(x){return x.id===id;});
  UI.toast('正在执行检查任务「'+d.name+'」...', 'info');
  setTimeout(function(){
    var bad = d.lastResult==='fail';
    d.lastRun = now+' 23:05'; d.lastResult = bad?'fail':'success';
    UI.modal({title:'执行结果 - '+d.name, w:'w-md', footer:'<button class="btn" onclick="UI.closeModal();App.resolve()">关闭</button>', body:
      UI.timeline([{title:'任务启动', body:'调度触发，加载规则 '+d.rules+' 条', time:'23:05:00'},
        {title:'规则执行', body:'逐条执行 SQL 检核，强规则优先', time:'23:05:02'},
        {title:'结果判定', cls:bad?'err':'ok', body: bad? 'QC-R-012 失败：异常 12 行 → 已生成异常单 QE20260912-001，弱规则通过' : '全部规则通过', time:'23:05:08'},
        {title:bad?'下游阻断':'下游放行', cls:bad?'err':'ok', body: bad? '强规则失败，联动 ETL 下游节点已阻断，并触发告警（QA01 邮件+短信）' : '检查通过，允许下游任务继续', time:'23:05:09'}])});
    App.resolve();
  }, 1200);
};
A.qtRules = function(id){
  var d = DB.qcTasks.find(function(x){return x.id===id;});
  var linked = DB.qcRules.filter(function(r){return r.linkTask===d.id;});
  UI.drawer({title:'编排规则 - '+d.name, w:'w-lg', body:
    '<div class="lock-tip" style="margin-bottom:10px">勾选需要纳入本任务的规则；强规则失败将阻断联动 ETL 下游。</div>'
    + DB.qcRules.map(function(r){
      var on = r.linkTask===d.id;
      var dim = DB.qcDims.find(function(x){return x.code===r.dim;})||{};
      return '<label style="display:flex;gap:8px;align-items:center;padding:8px 10px;border:1px solid var(--border);border-radius:8px;margin-bottom:7px;cursor:pointer"><input type="checkbox" class="qt-rk" value="'+r.id+'" '+(on?'checked':'')+'><span class="tag" style="background:'+(dim.color||'#1668dc')+'18;color:'+(dim.color||'#1668dc')+'">'+dim.name+'</span><span style="font-size:12px">'+r.name+'</span><span style="margin-left:auto">'+tag(r.level, r.level==='强规则'?'red':'orange')+'</span></label>';
    }).join(''),
    onOk:function(){
      var vals = Array.prototype.map.call(document.querySelectorAll('.qt-rk:checked'), function(e){return e.value;});
      DB.qcRules.forEach(function(r){ if(r.linkTask===d.id) r.linkTask='-'; if(vals.indexOf(r.id)>=0) r.linkTask=d.id; });
      d.rules = vals.length;
      UI.toast('已编排 '+vals.length+' 条规则', 'success');
    }});
};

/* ---- 异常数据核查 ---- */
App.reg('#/qc/exception', '异常数据核查', function(){
  var html = UI.pageHead('异常数据核查',
    '检查失败生成的异常单：查看异常样本 → 核查定责 → 修复（生成清理SQL）或忽略（豁免留痕）→ 归档闭环',
    '<button class="btn" onclick="UI.toast(\'异常数据已同步至隔离区（/data/quarantine），可下载分析\',\'info\')">隔离区查看</button>',
    '操作指引：① 每张异常单可先看「样本」定位异常行；② 修复将生成清理 SQL 并关联整改任务，复检通过后自动闭环；③ 忽略需填写豁免原因并留痕；④ 在「质量流图」页可按异常单反查工作流节点。异常单状态流转见下方状态图。');
  html += UI.stateFlow([
    {k:'pending', t:'待处理',  d:'检查失败 · 待定责'},
    {k:'fixing',  t:'整改中',  d:'清理SQL · 关联任务'},
    {k:'done',    t:'已处置',  d:'已修复 / 豁免忽略'},
    {k:'closed',  t:'已归档',  d:'复检通过 · 闭环留痕'}
  ], null, '闭环说明：待处理 →（修复或忽略）→ 已处置 →（复检/豁免审批通过）→ 已归档；未闭环异常会在质量流图上持续标红并阻塞产出表质量评分。');
  html += '<div class="grid grid-3" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#d97706">⚑</span><div><div class="stat-num">'+DB.qcExceptions.filter(function(e){return e.status==='pending';}).length+'</div><div class="stat-label">待处理</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+DB.qcExceptions.filter(function(e){return e.status==='fixed';}).length+'</div><div class="stat-label">已修复</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#475569">⊘</span><div><div class="stat-num">'+DB.qcExceptions.filter(function(e){return e.status==='ignored';}).length+'</div><div class="stat-label">已忽略（豁免）</div></div></div></div>';
  html += UI.card('异常单列表', UI.tbl({
    id:'t_qe', rowKey:'id', pageSize:8, searchKeys:['id','ruleName','table'], searchPh:'搜索单号/规则/表',
    filters:[{k:'status', label:'状态', options:[{v:'pending',t:'待处理'},{v:'fixed',t:'已修复'},{v:'ignored',t:'已忽略'}]}],
    data:function(){ return DB.qcExceptions; },
    cols:[
      {t:'异常单', k:'id', render:function(r){return '<b>'+r.id+'</b><div style="font-size:11px;color:var(--text-3)">检查单 '+r.qcId+'</div>';}},
      {t:'规则', k:'ruleName', render:function(r){return r.ruleName+'<div style="font-size:11px;color:var(--text-3)">'+r.ruleId+'</div>';}},
      {t:'表.字段', render:function(r){return '<span class="mono" style="font-size:11.5px">'+r.table+'.'+r.field+'</span>';}},
      {t:'维度', k:'dim'},
      {t:'异常数', k:'cnt', render:function(r){return '<b style="color:var(--danger)">'+r.cnt+'</b>';}},
      {t:'数据日期', k:'dt'},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.qeDetail(\''+r.id+'\')">样本</a>'
        +(r.status==='pending'? '<a onclick="A.qeFix(\''+r.id+'\')">修复</a><a onclick="A.qeIgnore(\''+r.id+'\')">忽略</a>':'');
    }}));
  return html;
});
A.qeDetail = function(id){
  var e = DB.qcExceptions.find(function(x){return x.id===id;});
  var keys = e.sample.length? Object.keys(e.sample[0]) : [];
  UI.modal({title:'异常样本 - '+e.id, w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.desc([['规则', e.ruleName+'（'+e.ruleId+'）'],['表.字段','<span class="mono">'+e.table+'.'+e.field+'</span>'],['维度', e.dim],['异常数','<b style="color:var(--danger)">'+e.cnt+'</b> 行'],['数据日期', e.dt]])
    + '<div class="table-wrap" style="margin-top:10px"><table class="tbl"><thead><tr>'+keys.map(function(k){return '<th>'+k+'</th>';}).join('')+'</tr></thead><tbody>'
    + e.sample.map(function(row){ return '<tr>'+keys.map(function(k){return '<td><span class="mono">'+UI.esc(row[k]==null?'NULL':row[k])+'</span></td>';}).join('')+'</tr>'; }).join('')
    + '</tbody></table></div><div class="lock-tip">异常数据已同步至隔离区 /data/quarantine/'+e.dt+'，修复动作将生成清理 SQL 供审批执行。</div>'});
};
A.qeFix = function(id){
  var e = DB.qcExceptions.find(function(x){return x.id===id;});
  UI.drawer({title:'修复异常 - '+e.id, w:'w-lg', body:
    '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>规则：'+e.ruleName+' · 表 <b class="mono">'+e.table+'.'+e.field+'</b> · 异常 '+e.cnt+' 行</span></div>'
    + UI.fRadio('修复方式', 'qe_way', [{v:'clean',t:'生成清理SQL（删除/订正异常行）'},{v:'patch',t:'回补源数据后重跑分区'},{v:'transfer',t:'流转修复工单给负责人'}], 'clean')
    + UI.fTextarea('修复说明', 'qe_note', {rows:2, req:true, ph:'如：负值金额为测试数据，按 pay_id 清理'}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.qeFixSave(\''+id+'\')">执行修复</button>'});
};
A.qeFixSave = function(id){
  var e = DB.qcExceptions.find(function(x){return x.id===id;});
  if(!UI.val('qe_note')){ UI.toast('请填写修复说明', 'warn'); return; }
  var way = UI.radioVal('qe_way','clean');
  UI.toast('正在执行修复（'+(way==='clean'?'清理SQL':way==='patch'?'回补重跑':'工单流转')+'）...', 'info');
  setTimeout(function(){
    e.status = 'fixed';
    UI.toast('修复完成：异常 '+e.cnt+' 行已处理，状态更新为「已修复」，已通知报告重算', 'success');
    App.resolve();
  }, 1000);
};
A.qeIgnore = function(id){
  var e = DB.qcExceptions.find(function(x){return x.id===id;});
  UI.drawer({title:'忽略异常 - '+e.id, body: UI.fTextarea('忽略理由（必填，审计留痕）', 'qe_ig', {rows:3, req:true}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn" onclick="A.qeIgnoreSave(\''+id+'\')">确认忽略</button>'});
};
A.qeIgnoreSave = function(id){
  var e = DB.qcExceptions.find(function(x){return x.id===id;});
  if(!UI.val('qe_ig')){ UI.toast('请填写忽略理由', 'warn'); return; }
  e.status = 'ignored';
  UI.toast('异常已忽略并留痕（下次检查不再生成同类异常单）', 'info'); App.resolve();
};

/* ---- 质量报告 ---- */
App.reg('#/qc/report', '质量报告', function(){
  var html = UI.pageHead('质量报告',
    '日报/周报/月报自动生成：评分、问题清单、修复闭环率，支持导出归档',
    '<button class="btn btn-primary" onclick="A.qrGen()">+ 生成报告</button>');
  html += UI.card('报告列表', UI.tbl({
    id:'t_qrep', rowKey:'id', pageSize:8, searchKeys:['id','name'], searchPh:'搜索报告',
    filters:[{k:'type', label:'类型', options:[{v:'日报',t:'日报'},{v:'周报',t:'周报'},{v:'月报',t:'月报'}]}],
    data:function(){ return DB.qcReports; },
    cols:[
      {t:'报告', k:'name', render:function(r){return '<a onclick="A.qrepView(\''+r.id+'\')"><b>'+r.name+'</b></a>';}},
      {t:'类型', k:'type', render:function(r){return tag(r.type, r.type==='日报'?'blue':r.type==='周报'?'purple':'green');}},
      {t:'周期', k:'period'},
      {t:'评分', k:'score', render:function(r){return '<b style="color:'+(r.score>=95?'var(--success)':r.score>=90?'var(--warn)':'var(--danger)')+'">'+r.score+'</b>';}},
      {t:'问题数', k:'problems'},
      {t:'已修复', k:'fixed'},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.qrepView(\''+r.id+'\')">查看</a><a onclick="A.qrepExport(\''+r.id+'\')">导出</a>';
    }}));
  return html;
});
A.qrGen = function(){
  UI.confirm({title:'生成质量报告', msg:'基于最近检查结果生成新的质量日报？', detail:'汇总今日检查任务结果、异常单闭环情况与评分。', onOk:function(){
    var id = 'QR-'+now.replace(/-/g,'')+'-X';
    var pending = DB.qcExceptions.filter(function(e){return e.status==='pending';}).length;
    DB.qcReports.unshift({id:id, name:'数据质量日报 '+now, type:'日报', period:now, score:95-pending, problems:pending+2, fixed:1, status:'published'});
    UI.toast('报告已生成：'+id, 'success'); App.resolve();
  }});
};
A.qrepView = function(id){
  var r = DB.qcReports.find(function(x){return x.id===id;});
  UI.modal({title:'质量报告 - '+r.name, w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="A.qrepExport(\''+r.id+'\')">导出PDF</button>', body:
    UI.desc([['报告编号', r.id],['类型', r.type],['统计周期', r.period],['综合评分','<b style="font-size:16px;color:'+(r.score>=95?'var(--success)':'var(--warn)')+'">'+r.score+'</b>'],['发现问题', r.problems+' 个'],['已修复闭环', r.fixed+' 个']])
    + Charts.bars({labels:['完整','准确','一致','及时','唯一','有效'], series:[{name:'得分', color:'#1668dc', data:DB.qcDimScore.map(function(d){return d.score;})}], h:200})
    + UI.timeline([
      {cls:'ok', title:'检查执行', body:'3 个检查任务 / 7 条规则全部调度执行', time:r.period+' 04:00'},
      {cls:'err', title:'问题发现', body:'QC-R-012 支付金额范围检查失败（12 行异常）等 '+r.problems+' 个问题', time:r.period+' 04:01'},
      {cls:'warn', title:'异常核查', body:'生成异常单并通知负责人，已修复 '+r.fixed+' 个，待处理 '+(r.problems-r.fixed)+' 个', time:r.period+' 09:00'},
      {cls:'ok', title:'报告归档', body:'报告发布并推送订阅人', time:r.period+' 09:10'}])});
};
A.qrepExport = function(id){
  var r = DB.qcReports.find(function(x){return x.id===id;});
  UI.download(r.name+'.txt', 'Datara 质量报告\n'+r.name+'\n评分：'+r.score+'\n问题：'+r.problems+' / 已修复：'+r.fixed+'\n六维得分：'+DB.qcDimScore.map(function(d){return d.name+'='+d.score;}).join('， '));
};

/* ---- 质量告警 ---- */
App.reg('#/qc/alarm', '质量告警', function(){
  var html = UI.pageHead('质量告警', '告警策略：强规则失败即时告警 / 弱规则汇总告警 / 评分阈值告警，多渠道触达',
    '<button class="btn btn-primary" onclick="A.qaCreate()">+ 新建告警策略</button>');
  html += UI.card('告警策略', UI.tbl({
    id:'t_qa', rowKey:'id', pageSize:8, searchKeys:['id','name','scope'], searchPh:'搜索策略',
    data:function(){ return DB.qcAlarms; },
    cols:[
      {t:'策略', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+'</div>';}},
      {t:'范围', k:'scope'},
      {t:'触发条件', k:'threshold'},
      {t:'渠道', k:'channel', render:function(r){return r.channel.split('+').map(function(c){return tag(c,'blue');}).join(' ');}},
      {t:'接收人', k:'receivers'},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.qaEdit(\''+r.id+'\')">编辑</a>'
        +'<a onclick="UI.toggleStatus(DB.qcAlarms.find(function(x){return x.id===\''+r.id+'\'}))">'+(r.status==='enabled'?'停用':'启用')+'</a>'
        +'<a onclick="A.qaFire(\''+r.id+'\')">模拟触发</a>'
        +'<a class="danger" onclick="UI.delRow(DB.qcAlarms, \'id\', \''+r.id+'\', \''+r.name+'\')">删除</a>';
    }}));
  return html;
});
A.qaFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('策略名称', 'qa_name', {value:d.name, req:true})
    + UI.fInput('生效范围', 'qa_scope', {value:d.scope, ph:'如：所有强规则失败 / WF001'})
    + UI.fInput('触发条件', 'qa_th', {value:d.threshold, req:true})
    + UI.fCheckGroup('通知渠道', 'qa_ch', [{v:'邮件',t:'邮件'},{v:'短信',t:'短信'},{v:'飞书',t:'飞书'}], (d.channel||'邮件').split('+'))
    + UI.fInput('接收人', 'qa_recv', {value:d.receivers})
    + '</div>';
};
A.qaCreate = function(){ UI.drawer({title:'新建告警策略', w:'w-lg', body:A.qaFormFields({}), onOk:function(){
  var name = UI.val('qa_name');
  if(!name){ UI.toast('请填写策略名称', 'warn'); return false; }
  DB.qcAlarms.push({id:'QA0'+(DB.qcAlarms.length+1), name:name, scope:UI.val('qa_scope'), threshold:UI.val('qa_th'), channel:UI.checkVals('qa_ch').join('+')||'邮件', receivers:UI.val('qa_recv'), status:'enabled'});
  UI.toast('告警策略已创建', 'success'); }}); };
A.qaEdit = function(id){ var d = DB.qcAlarms.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑告警策略 - '+d.name, w:'w-lg', body:A.qaFormFields(d), onOk:function(){
    Object.assign(d, {name:UI.val('qa_name'), scope:UI.val('qa_scope'), threshold:UI.val('qa_th'), channel:UI.checkVals('qa_ch').join('+')||'邮件', receivers:UI.val('qa_recv')});
    UI.toast('告警策略已保存', 'success'); }}); };
A.qaFire = function(id){
  var d = DB.qcAlarms.find(function(x){return x.id===id;});
  UI.modal({title:'模拟告警触发 - '+d.name, w:'w-sm', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    '<div class="checker-line err"><span>⚠</span><div><b>['+d.channel+'] 质量告警</b><div style="font-size:11.5px;margin-top:3px">触发条件：'+d.threshold+'<br>接收人：'+d.receivers+'</div></div></div><div class="lock-tip">模拟触发不发送真实消息。</div>'});
};

/* ---- 质量流图（质量-任务流图联动） ----
   引用 DAG 工作流（M13 DB.workflows.nodesDetail）：
   · 总体全景 = 聚合全部工作流 DAG + tableDeps 跨流表依赖串联
   · 单工作流 = 该任务流图；节点按产出表质量结果标记（未关闭异常 → err，否则 ok）
   · 点节点弹规则对标表单；右侧异常单点击定位画布节点 */
A.QF_TYPE_META = {
  'ETL节点':{i:'⛃', c:'#0891b2'}, 'SQL节点':{i:'⌨', c:'#1668dc'}, '脚本节点':{i:'ƒ', c:'#7c3aed'},
  '子工作流':{i:'⑃', c:'#d97706'}, '依赖检查':{i:'⛓', c:'#94a3b8'}
};
A.qcTabs = function(cur){
  function t(label, on, oc){ return '<span class="tab'+(on?' on':'')+'" onclick="'+oc+'">'+label+'</span>'; }
  var scoreOn = cur==='score', taskOn = cur==='task';
  return '<div class="tabs">'
    + t('质量评分卡', scoreOn, scoreOn? 'A.qfShowMain(this)':'App.go(\'#/qc/score\')')
    + t('检查任务', taskOn, taskOn? 'A.qfShowMain(this)':'App.go(\'#/qc/task\')')
    + t('质量流图', false, 'A.qfTab(this)')
    + '</div>';
};
A.qfShowMain = function(el){
  if(el && el.parentNode) Array.prototype.forEach.call(el.parentNode.children, function(t){ t.classList.remove('on'); });
  if(el) el.classList.add('on');
  var m = document.getElementById('qcTabMain'), f = document.getElementById('qcTabFlow');
  if(m) m.style.display = ''; if(f) f.style.display = 'none';
};
A.qfTab = function(el){
  if(el && el.parentNode) Array.prototype.forEach.call(el.parentNode.children, function(t){ t.classList.remove('on'); });
  if(el) el.classList.add('on');
  var m = document.getElementById('qcTabMain'), f = document.getElementById('qcTabFlow');
  if(m) m.style.display = 'none'; if(f) f.style.display = '';
  setTimeout(A.qfInit, 30);
};
A.qfFlowPanel = function(){
  var items = DB.qcExceptions.map(function(e){
    var pend = e.status==='pending';
    return '<div onclick="A.qfLocate(\''+e.id+'\')" style="border:1px solid '+(pend?'var(--danger)':'var(--border)')+';border-left:3px solid '+(pend?'var(--danger)':'var(--border-strong)')+';border-radius:8px;padding:8px 10px;margin-bottom:7px;cursor:pointer;background:'+(pend?'#fff7f7':'#fff')+'">'
      + '<div style="display:flex;align-items:center;gap:6px"><b style="font-size:12px">'+e.id+'</b><span style="margin-left:auto">'+st(e.status)+'</span></div>'
      + '<div style="font-size:11.5px;margin-top:3px">'+UI.esc(e.ruleName)+'</div>'
      + '<div class="mono" style="font-size:10.5px;color:var(--text-3);margin-top:2px">'+e.table+'.'+e.field+' · 异常 '+e.cnt+' 行 · '+e.dt+'</div>'
      + '</div>';
  }).join('');
  return '<div id="qcTabFlow" style="display:none">'
    + '<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">'
    +   '<span style="font-size:12.5px;color:var(--text-2)">检核范围</span>'
    +   '<select id="qfSel" onchange="A.qfDraw(this.value)" style="padding:6px 10px;border:1px solid var(--border-strong);border-radius:8px;font-size:12.5px;background:#fff;min-width:230px">'
    +     '<option value="__ALL__">总体全景流图（聚合全部工作流）</option>'
    +     DB.workflows.map(function(w){ return '<option value="'+w.id+'">'+UI.esc(w.name)+'（'+w.id+' · '+w.nodes+' 节点 · '+(w.status==='online'?'已上线':'草稿')+'）</option>'; }).join('')
    +   '</select>'
    +   '<span id="qfStats" style="font-size:12px"></span>'
    +   '<span style="flex:1"></span>'
    +   '<span style="font-size:11.5px;color:var(--text-3)">节点 ✓/! 为质量标记 · 点击节点看规则对标 · 右侧异常单点击定位节点</span>'
    + '</div>'
    + '<div class="etl-main" style="margin-top:10px">'
    +   '<div id="qfMount"></div>'
    +   '<div class="etl-right" style="max-height:none">'
    +     '<div class="etl-right-h">质量异常记录（'+DB.qcExceptions.length+'）· 点击定位左栏节点</div>'
    +     '<div class="etl-right-b">'+(items || '<div class="empty" style="padding:20px"><p>暂无异常记录</p></div>')+'</div>'
    +   '</div>'
    + '</div>'
    + '<div class="lock-tip">质量流图引用 DAG 工作流任务图（M13）：总体模式聚合各工作流并按跨流表依赖（T-1/T）串联；节点标记 = 产出表存在「待处理」质量异常 → 红 !（异常），否则绿 ✓（正常）；规则对标取自质量规则与异常记录。</div>'
    + '</div>';
};
A.qfTableOf = function(out){
  if(!out || out==='-') return null;
  for(var i=0;i<DB.metaTables.length;i++){ if(out.indexOf(DB.metaTables[i].name)===0) return DB.metaTables[i].name; }
  return null;
};
A.qfOpenCnt = function(table){
  return DB.qcExceptions.filter(function(e){ return e.table===table && e.status==='pending'; }).length;
};
A.qfBuild = function(view){
  var nodes = [], edges = [], bandY = 24;
  var wfs = view==='__ALL__'? DB.workflows : DB.workflows.filter(function(w){ return w.id===view; });
  wfs.forEach(function(wf){
    var sub = wf.nodesDetail.map(function(nd){
      var meta = A.QF_TYPE_META[nd.type] || {i:'▣', c:'#1668dc'};
      var table = A.qfTableOf(nd.outTable);
      var rules = table? DB.qcRules.filter(function(r){ return r.table===table; }) : [];
      var open = table? A.qfOpenCnt(table) : 0;
      var sum = '产出 '+(table||'—（无直接产出表）');
      if(rules.length) sum += ' · 检核 '+rules.length+' 条规则';
      sum += open? ' · 未关闭异常 '+open+' 条（点击节点查看对标）' : (rules.length? ' · 检核通过' : ' · 未挂接质量规则');
      return {id:wf.id+'_'+nd.id, name:nd.name, type:nd.type, icon:meta.i, color:meta.c,
        wfId:wf.id, wfName:wf.name, table:table, open:open,
        summary:sum, mark: open? 'err':'ok',
        cfg:{'产出表':nd.outTable||'-', '质量规则':rules.length+' 条', '未关闭异常':open+' 条'}, x:0, y:0};
    });
    var idx = {}; sub.forEach(function(n){ idx[n.id]=n; });
    var subE = [];
    wf.nodesDetail.forEach(function(nd){
      (nd.dep||[]).forEach(function(d){ if(idx[wf.id+'_'+d]) subE.push({from:wf.id+'_'+d, to:wf.id+'_'+nd.id, kind:'flow'}); });
    });
    VC.autoPos(sub, subE);
    var maxY = 0;
    sub.forEach(function(n){ n.x += 24; n.y += bandY; if(n.y+46>maxY) maxY = n.y+46; });
    nodes = nodes.concat(sub); edges = edges.concat(subE);
    bandY = maxY + 84;
  });
  if(view==='__ALL__'){
    DB.tableDeps.forEach(function(d){
      var up = null, dn = null;
      nodes.forEach(function(n){
        if(!up && n.wfId===d.up.wf && n.name===d.up.task) up = n;
        if(!dn && n.wfId===d.down.wf && n.name===d.down.task) dn = n;
      });
      if(up && dn) edges.push({from:up.id, to:dn.id, kind:'dep', label:d.table+'（'+d.period+'）'});
    });
  }
  return {nodes:nodes, edges:edges};
};
A.qfDraw = function(view){
  A._qfView = view;
  var d = A.qfBuild(view);
  A._qfNodes = d.nodes;
  if(!A._qfVc || !document.getElementById(A._qfVc)){
    A._qfVc = VC.create({mount:'qfMount', nodes:d.nodes, edges:d.edges, editable:false, height:600, mode:'view',
      legendExtra:[{c:'#16a34a', t:'正常（检核通过）'}, {c:'#e5484d', t:'异常（存在未关闭异常）'}],
      onNodeClick:function(n){ A.qfNodeClick(n); }});
  } else {
    VC.setData(A._qfVc, d);
  }
  var err = d.nodes.filter(function(n){ return n.mark==='err'; }).length;
  var box = document.getElementById('qfStats');
  if(box) box.innerHTML = '<span style="color:var(--success)">● 正常 '+(d.nodes.length-err)+'</span>&nbsp;·&nbsp;<span style="color:var(--danger)">● 异常 '+err+'</span>&nbsp;·&nbsp;节点 '+d.nodes.length+' / 连线 '+d.edges.length;
};
A.qfInit = function(){
  if(!document.getElementById('qfMount')) return;
  var sel = document.getElementById('qfSel');
  A.qfDraw(sel && sel.value? sel.value : '__ALL__');
};
/* 实际值 vs 阈值（演示对标：失败规则取异常单，通过规则按阈值给演示实际值） */
A.qfActual = function(r){
  if(r.lastResult==='fail'){
    var ex = null;
    DB.qcExceptions.forEach(function(e){ if(!ex && e.ruleId===r.id && e.status==='pending') ex = e; });
    return {pass:false, text: ex? ('异常 '+ex.cnt+' 行（样本 -320.50 ~ 890,000.00）') : '超出阈值（演示）', pct:72};
  }
  var m = {'重复数 = 0':'重复 0 行', '=0 重复':'重复 0 行', '空值率 ≤ 1%':'空值率 0.12%', '值域 ∈ {M,F}':'非法 0 行',
    '与ods_gdb_biz_pay_record SUM差 ≤ 0.01':'差额 0.00', '每日04:00前产出':'03:58 产出', '日环比波动 ≤ ±30%':'波动 +6.2%',
    '非法值 = 0':'非法 0 行', '0 ≤ 值 ≤ 500000':'全部在值域内'};
  return {pass:true, text:m[r.threshold]||'符合阈值', pct:100};
};
A.qfNodeClick = function(n){
  var table = n.table;
  var rules = table? DB.qcRules.filter(function(r){ return r.table===table; }) : [];
  var isDemo = !rules.length;
  if(isDemo) rules = [
    {id:'QC-DEMO-01', name:'主键唯一性（演示）', dim:'UNIQUENESS', type:'唯一性检查', threshold:'重复数 = 0', level:'弱规则', lastResult:'pass'},
    {id:'QC-DEMO-02', name:'行数日环比波动（演示）', dim:'COMPLETENESS', type:'行数波动', threshold:'日环比波动 ≤ ±30%', level:'弱规则', lastResult:'pass'},
    {id:'QC-DEMO-03', name:'枚举值合法性（演示）', dim:'VALIDITY', type:'枚举检查', threshold:'非法值 = 0', level:'强规则', lastResult:'pass'}];
  var dims = {}; DB.qcDims.forEach(function(d){ dims[d.code]=d; });
  var rows = rules.map(function(r){
    var a = A.qfActual(r);
    var dim = dims[r.dim] || {name:r.dim, color:'#1668dc'};
    return '<div style="border:1px solid var(--border);border-radius:8px;padding:9px 11px;margin-bottom:8px">'
      + '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><b style="font-size:12.5px">'+UI.esc(r.name)+'</b>'
      + '<span class="tag" style="background:'+dim.color+'18;color:'+dim.color+'">'+dim.name+'</span>'
      + tag(r.level, r.level==='强规则'?'red':'orange')
      + '<span style="margin-left:auto">'+(a.pass? st('pass'):'<span class="st st-red"><i class="dot"></i>失败</span>')+'</span></div>'
      + '<div style="display:flex;gap:14px;font-size:11.5px;color:var(--text-2);margin-top:5px;flex-wrap:wrap">'
      + '<span>阈值：<b class="mono">'+UI.esc(r.threshold)+'</b></span>'
      + '<span>实际：<b class="mono" style="color:'+(a.pass?'var(--success)':'var(--danger)')+'">'+UI.esc(a.text)+'</b></span>'
      + '<span style="color:var(--text-3)">'+r.id+' · '+r.type+'</span></div>'
      + '<div style="display:flex;align-items:center;gap:10px;margin-top:7px">'
      + '<div class="progress '+(a.pass?'green':'red')+'" style="flex:1"><div class="bar" style="width:'+a.pct+'%"></div></div>'
      + '<span style="font-size:10.5px;color:var(--text-3);white-space:nowrap">实际/阈值对标 '+(a.pass?'达标':'未达标')+'</span></div>'
      + '</div>';
  }).join('');
  var exs = table? DB.qcExceptions.filter(function(e){ return e.table===table; }) : [];
  var exHtml = exs.length? exs.map(function(e){
    return '<div class="banner '+(e.status==='pending'?'banner-danger':'banner-info')+'" style="margin-bottom:6px;padding:8px 11px">'
      + '<span class="b-ico">'+(e.status==='pending'?'⚑':'ℹ')+'</span>'
      + '<span style="font-size:12px">'+e.id+' · '+UI.esc(e.ruleName)+' · 异常 <b style="color:var(--danger)">'+e.cnt+'</b> 行 · '+e.dt+' · '+st(e.status)+'</span></div>';
  }).join('') : '<div class="banner banner-success" style="padding:8px 11px"><span class="b-ico">✓</span><span style="font-size:12px">无质量异常记录，检核全部通过</span></div>';
  UI.modal({title:'节点质量对标 - '+n.name, w:'w-lg',
    footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>'
      +'<button class="btn btn-primary" onclick="UI.closeModal();App.go(\'#/qc/exception\')">去处理</button>', body:
    UI.desc([['节点', UI.esc(n.name)+'（'+n.type+'）'], ['所属工作流', UI.esc(n.wfName)+'（'+n.wfId+'）'],
      ['产出表','<span class="mono">'+UI.esc(n.cfg['产出表'])+'</span>'],
      ['检核结论', n.open? '<b style="color:var(--danger)">存在未关闭异常 '+n.open+' 条</b>' : '<b style="color:var(--success)">正常（检核通过）</b>']])
    + (isDemo? '<div class="banner banner-info" style="margin-bottom:10px"><span class="b-ico">ℹ</span><span>该节点产出表暂无质量规则，以下为演示对标数据。</span></div>':'')
    + '<div style="font-size:12.5px;font-weight:700;margin:4px 0 8px">质量规则清单与实际对标（'+rules.length+' 条）</div>'
    + rows
    + '<div style="font-size:12.5px;font-weight:700;margin:12px 0 8px">异常摘要</div>'
    + exHtml});
};
A.qfFlash = function(nid){
  var nd = document.getElementById(A._qfVc+'_n_'+nid);
  if(!nd) return;
  nd.classList.remove('vc-hl');
  void nd.offsetWidth; /* 重排以重触发闪烁动画 */
  nd.classList.add('vc-hl');
};
A.qfLocate = function(exId){
  var e = DB.qcExceptions.find(function(x){ return x.id===exId; });
  if(!e) return;
  var hit = A._qfNodes? A._qfNodes.filter(function(n){ return n.table===e.table; })[0] : null;
  if(!hit){
    var wfId = null;
    DB.workflows.forEach(function(w){
      w.nodesDetail.forEach(function(nd){ if(!wfId && A.qfTableOf(nd.outTable)===e.table) wfId = w.id; });
    });
    if(!wfId){ UI.toast('该异常表（'+e.table+'）未关联工作流产出节点', 'warn'); return; }
    var sel = document.getElementById('qfSel'); if(sel) sel.value = wfId;
    A.qfDraw(wfId);
    hit = A._qfNodes.filter(function(n){ return n.table===e.table; })[0];
  }
  if(!hit){ UI.toast('未在当前流图中找到对应节点', 'warn'); return; }
  VC.highlight(A._qfVc, hit.id);
  A.qfFlash(hit.id);
  UI.toast('已定位节点「'+hit.name+'」· '+hit.wfName+'（产出 '+e.table+'）', 'success');
};
})();
