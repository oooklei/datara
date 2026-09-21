/* ============================================================
   M03 数据源管理（P0：注册连接/连接池/数据源探索/分组标签/连接诊断）
   ============================================================ */
(function(){
App.reg('#/ds/list', '数据源管理', function(){
  var html = UI.pageHead('数据源管理',
    '统一注册与接入各类数据源（万里/高斯/达梦/MySQL/Oracle/数仓引擎/Kafka），支撑后续同步、建模、开发（P0·收敛保障类型）',
    '<button class="btn btn-primary" onclick="A.dsCreate()">+ 注册数据源</button>'
    +'<button class="btn" onclick="UI.toast(\'已刷新数据源状态\',\'info\');App.resolve()">刷新状态</button>'
    +'<button class="btn" onclick="A.dsBatchTag()">批量分组标签</button>');
  html += UI.card('数据源列表', UI.tbl({
    id:'t_ds', rowKey:'id', pageSize:8, selectable:true, searchKeys:['name','type','host','group','id'], searchPh:'搜索名称/类型/主机',
    filters:[
      {k:'env', label:'环境', options:[{v:'生产',t:'生产'},{v:'测试',t:'测试'},{v:'开发',t:'开发'}]},
      {k:'group', label:'业务分组', options:[{v:'交易域',t:'交易域'},{v:'经营域',t:'经营域'},{v:'财务域',t:'财务域'},{v:'数仓',t:'数仓'},{v:'消息',t:'消息'}]},
      {k:'status', label:'状态', options:[{v:'enabled',t:'已启用'},{v:'disabled',t:'已停用'}]}
    ],
    data:function(){ return DB.datasources; },
    cols:[
      {t:'数据源', k:'name', sortable:true, render:function(r){
        var t = DB.dsTypes.find(function(x){return x.name===r.type;}) || {};
        return '<div style="display:flex;gap:9px;align-items:center"><span class="type-icon" style="background:'+(t.color||'#1668dc')+';width:30px;height:30px;font-size:10px">'+UI.esc((r.type||'?').slice(0,2).toUpperCase())+'</span>'
          +'<div><a onclick="App.go(\'#/ds/detail/'+r.id+'\')"><b>'+UI.esc(r.name)+'</b></a><div style="color:var(--text-3);font-size:11px">'+r.id+' · '+UI.esc(r.type)+(t.xc?' <span class="tag tag-xc" style="height:17px">信创</span>':'')+'</div></div></div>';
      }},
      {t:'主机', k:'host', render:function(r){ return '<span class="mono">'+UI.esc(r.host)+':'+r.port+'</span><div style="color:var(--text-3);font-size:11px">'+UI.esc(r.db)+'</div>'; }},
      {t:'环境', k:'env', render:function(r){ return tag(r.env, r.env==='生产'?'red':(r.env==='测试'?'orange':'cyan')); }},
      {t:'分组', k:'group'},
      {t:'标签', render:function(r){ return (r.tags||[]).map(function(t){return tag(t,'blue');}).join(' ') || '<span style="color:var(--text-3)">-</span>'; }},
      {t:'健康/延迟', render:function(r){
        var ok = r.health==='健康';
        return '<span class="st '+(ok?'st-green':'st-orange')+'"><i class="dot"></i>'+r.health+'</span><div style="font-size:11px;color:var(--text-3)">'+r.latency+' ms</div>';
      }},
      {t:'状态', k:'status', render:function(r){ return st(r.status); }}
    ],
    ops:function(r){
      return '<a onclick="A.dsTest(\''+r.id+'\')">测试</a>'
        +'<a onclick="App.go(\'#/ds/extract/'+r.id+'\')">抽取元数据</a>'
        +'<a onclick="App.go(\'#/ds/detail/'+r.id+'\')">详情</a>'
        +'<a onclick="A.dsEdit(\''+r.id+'\')">编辑</a>'
        +'<a onclick="UI.toggleStatus(DB.datasources.find(function(x){return x.id===\''+r.id+'\'}), function(){})">'+(r.status==='enabled'?'停用':'启用')+'</a>'
        +'<a class="danger" onclick="A.dsDel(\''+r.id+'\')">删除</a>';
    }
  }, null));
  return html;
});

/* 新建/编辑 抽屉表单 */
A.dsFormFields = function(d){
  var types = DB.dsTypes.map(function(t){return {v:t.name, t:t.name+(t.xc?'（信创）':'')};});
  return UI.fSelect('数据源类型', 'f_type', types, {value:d.type, req:true, onchange:'A.dsTypeChanged()'})
    + '<div class="form-grid">'
    + UI.fInput('数据源名称', 'f_name', {value:d.name, req:true, ph:'如：万里GreatDB-生产业务库'})
    + UI.fInput('主机地址', 'f_host', {value:d.host, req:true, ph:'IP或域名'})
    + UI.fInput('端口', 'f_port', {value:d.port, type:'number'})
    + UI.fInput('数据库名', 'f_db', {value:d.db})
    + UI.fInput('用户名', 'f_user', {value:d.user})
    + UI.fInput('密码', 'f_pwd', {value:'******', type:'password'})
    + UI.fSelect('环境', 'f_env', [{v:'生产',t:'生产'},{v:'测试',t:'测试'},{v:'开发',t:'开发'}], {value:d.env})
    + UI.fSelect('业务分组', 'f_group', ['交易域','经营域','财务域','商品域','数仓','消息','公共'], {value:d.group})
    + '</div>'
    + '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>凭证安全管理能力在 P0 范围外（一期暂缓），密码当前以加密串存储；信创环境（麒麟V10/鲲鹏920/万里数据库）已纳入开发联测基础。</span></div>';
};
A.dsCreate = function(){
  UI.drawer({ title:'注册数据源', w:'w-lg', body:A.dsFormFields({}) + UI.fSwitch('注册成功后自动探索库表结构', 'f_autoexplore', true, '形成数据源资产清单，用于元数据目录'),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn" onclick="A.dsTestForm()">测试连接</button><button class="btn btn-primary" onclick="A.dsSave()">保存</button>' });
};
A.dsEdit = function(id){
  var d = DB.datasources.find(function(x){return x.id===id;});
  UI.drawer({ title:'编辑数据源 - '+d.name, w:'w-lg', body:A.dsFormFields(d),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn" onclick="A.dsTestForm()">测试连接</button><button class="btn btn-primary" onclick="A.dsSave(\''+id+'\')">保存</button>' });
};
A.dsTypeChanged = function(){
  var t = DB.dsTypes.find(function(x){return x.name===UI.val('f_type');});
  if(t && document.getElementById('f_port')) document.getElementById('f_port').value = t.port;
};
A.dsTestForm = function(){
  UI.toast('正在测试连接 '+UI.val('f_host')+':'+UI.val('f_port')+' ...', 'info');
  setTimeout(function(){ UI.toast('连接成功！延迟 '+Math.floor(5+Math.random()*20)+' ms，账号权限校验通过', 'success'); }, 700);
};
A.dsSave = function(id){
  var name = UI.val('f_name');
  if(!name){ UI.toast('请填写数据源名称', 'warn'); return false; }
  if(id){
    var d = DB.datasources.find(function(x){return x.id===id;});
    Object.assign(d, {name:name, type:UI.val('f_type'), host:UI.val('f_host'), port:UI.val('f_port'), db:UI.val('f_db'), user:UI.val('f_user'), env:UI.val('f_env'), group:UI.val('f_group')});
    UI.toast('数据源「'+name+'」已保存', 'success');
  } else {
    var nid = 'DS'+String(DB.datasources.length+1).padStart(3,'0');
    DB.datasources.push({id:nid, name:name, type:UI.val('f_type'), host:UI.val('f_host'), port:UI.val('f_port')||3306, db:UI.val('f_db'), user:UI.val('f_user'), pwd:'******', env:UI.val('f_env'), group:UI.val('f_group'), tags:[], pool:{max:10,minIdle:1,idle:600,timeout:30}, status:'enabled', owner:DB.user.name, createdAt:'2026-09-12 22:35', latency:Math.floor(5+Math.random()*25), health:'健康'});
    UI.toast('数据源「'+name+'」注册成功，已自动探索库表结构', 'success');
  }
  UI.closeDrawer();
};
A.dsTest = function(id){
  var d = DB.datasources.find(function(x){return x.id===id;});
  UI.toast('正在对「'+d.name+'」执行连接诊断 ...', 'info');
  setTimeout(function(){
    UI.modal({title:'连接诊断结果 - '+d.name, w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
      '<div class="checker-line ok"><span>✓</span><b>网络连通</b><span style="margin-left:auto;color:var(--text-3)">TCP '+UI.esc(d.host)+':'+d.port+' 可达</span></div>'
      +'<div class="checker-line ok"><span>✓</span><b>账号认证</b><span style="margin-left:auto;color:var(--text-3)">用户 '+UI.esc(d.user)+' 权限校验通过</span></div>'
      +'<div class="checker-line ok"><span>✓</span><b>延迟探测</b><span style="margin-left:auto;color:var(--text-3)">'+d.latency+' ms</span></div>'
      +'<div class="checker-line ok"><span>✓</span><b>连接池</b><span style="margin-left:auto;color:var(--text-3)">活跃 '+(2+Math.floor(Math.random()*5))+'/'+d.pool.max+'，空闲回收正常</span></div>'});
  }, 800);
};
A.dsDel = function(id){
  var d = DB.datasources.find(function(x){return x.id===id;});
  var used = DB.syncBatches.some(function(b){return b.srcDs===id;}) || DB.etlTasks.length>0;
  if(used){
    UI.confirm({ title:'无法删除', danger:true, msg:'数据源「'+d.name+'」正被同步任务/采集任务引用', detail:'请先解除引用（删除相关同步批次或采集任务）后再删除。'});
  } else {
    UI.delRow(DB.datasources, 'id', id, d.name);
  }
};
A.dsBatchTag = function(){
  var sel = UI.selRows('t_ds');
  if(!sel.length){ UI.toast('请先在列表中勾选数据源', 'warn'); return; }
  UI.drawer({ title:'批量分组与标签（已选 '+sel.length+' 个）', body:
    UI.fSelect('业务分组', 'bt_group', ['交易域','经营域','财务域','商品域','数仓','消息','公共'], {})
    + UI.fInput('标签（逗号分隔）', 'bt_tags', {ph:'如：核心,联调'})
    + '<div class="f-help">标签分类体系：重要性（核心/高优先）、环境（生产/测试）、用途（联调/报表）等</div>',
    onOk:function(){
      var tags = UI.val('bt_tags')? UI.val('bt_tags').split(/[,，]/).map(function(s){return s.trim();}).filter(Boolean) : [];
      var grp = UI.val('bt_group');
      sel.forEach(function(id){ var d = DB.datasources.find(function(x){return x.id===id;}); if(!d) return; if(grp) d.group=grp; tags.forEach(function(t){ if(d.tags.indexOf(t)<0) d.tags.push(t); }); });
      UI.toast('已为 '+sel.length+' 个数据源更新分组标签', 'success');
    }});
};

/* ---- 数据源详情 ---- */
App.reg('#/ds/detail/:id', '数据源详情', function(p){
  var d = DB.datasources.find(function(x){return x.id===p.id;});
  if(!d) return '<div class="empty">数据源不存在</div>';
  var t = DB.dsTypes.find(function(x){return x.name===d.type;}) || {};
  var tabs = UI.tabs('dsTab', [
    {label:'概览', render:1},{label:'连接池管理', render:1},{label:'数据源探索', render:1},{label:'连接诊断', render:1},{label:'分组与标签', render:1}
  ], 0);
  var html = UI.pageHead('<a onclick="App.go(\'#/ds/list\')">← 数据源管理</a> / '+d.name,
    d.id+' · '+d.type+(t.xc?'（信创）':'')+' · 负责人 '+d.owner+' · 注册于 '+d.createdAt,
    '<button class="btn" onclick="A.dsTest(\''+d.id+'\')">连接诊断</button>'
    +'<button class="btn" onclick="A.dsEdit(\''+d.id+'\')">编辑</button>'
    +'<button class="btn" onclick="A.dsExplore(\''+d.id+'\')">重新探索</button>'
    + st(d.status));
  html += '<div class="card no-head"><div class="card-body">'+tabs+'<div id="dsTabBody"></div></div></div>';
  App.onAfterRender(function(m){ if(m.path.indexOf('#/ds/detail/')===0) A._dsTabRender(0, d); });
  UI._tabCb['dsTab'] = function(i){ A._dsTabRender(i, d); };
  return html;
});
A._dsTabRender = function(i, d){
  var body = document.getElementById('dsTabBody');
  if(i===0){ /* 概览 */
    body.innerHTML = UI.desc([
      ['数据源ID', d.id], ['类型', d.type], ['主机', '<span class="mono">'+UI.esc(d.host)+':'+d.port+'</span>'],
      ['数据库', d.db], ['用户名', d.user], ['密码', '******（加密存储）'],
      ['环境', tag(d.env, d.env==='生产'?'red':'orange')], ['业务分组', d.group],
      ['标签', (d.tags||[]).map(function(t){return tag(t,'blue');}).join(' ')||'-'],
      ['延迟', d.latency+' ms'], ['健康状态', st(d.status==='enabled'?'success':'disabled').replace('成功','健康')],
      ['负责人', d.owner]
    ]) + '<div class="card-head" style="border-bottom:none;padding:14px 0 8px"><h3>关联引用</h3></div>'
      + UI.tbl({id:'t_dsref', rowKey:'id', pageSize:5, searchKeys:['id','name'],
        data:function(){ return DB.syncBatches.filter(function(b){return b.srcDs===d.id;}).map(function(b){return {id:b.id, name:b.id+'（'+b.srcName+' → '+b.target+'）', type:'批量同步批次'};}); },
        cols:[{t:'引用对象',k:'name'},{t:'类型',k:'type'},{t:'操作',render:function(r){return '<a onclick="App.go(\'#/batch/board\')">查看批次</a>';}}],
        ops:null});
  }
  if(i===1){ /* 连接池 */
    body.innerHTML = UI.card('连接池参数（复用连接，降低建连开销）',
      '<div class="form-grid">'
      + UI.fInput('最大连接数 maxPoolSize', 'p_max', {value:d.pool.max, type:'number'})
      + UI.fInput('最小空闲连接 minIdle', 'p_min', {value:d.pool.minIdle, type:'number'})
      + UI.fInput('空闲回收时间(s)', 'p_idle', {value:d.pool.idle, type:'number'})
      + UI.fInput('获取超时(s)', 'p_timeout', {value:d.pool.timeout, type:'number'})
      + '</div><button class="btn btn-primary" onclick="A.dsPoolSave(\''+d.id+'\')">保存配置</button> '
      + '<button class="btn" onclick="UI.toast(\'连接池已重置：空闲连接已回收，活跃连接 \'+Math.floor(2+Math.random()*5),\'success\')">重置连接池</button>')
    + UI.card('实时连接状态', '<div class="grid grid-4">'
      +'<div class="stat-card"><div><div class="stat-num">'+(2+Math.floor(Math.random()*4))+'</div><div class="stat-label">活跃连接</div></div></div>'
      +'<div class="stat-card"><div><div class="stat-num">'+d.pool.max+'</div><div class="stat-label">最大连接</div></div></div>'
      +'<div class="stat-card"><div><div class="stat-num">'+Math.floor(Math.random()*30)+' ms</div><div class="stat-label">平均获取耗时</div></div></div>'
      +'<div class="stat-card"><div><div class="stat-num">0.0%</div><div class="stat-label">获取失败率</div></div></div></div>');
  }
  if(i===2){ /* 探索 */
    var libs = [{db:'gdb_main', tables:[{n:'user_info',c:8,rows:1250000},{n:'trade_order',c:12,rows:4100000},{n:'pay_record',c:10,rows:2600000}]},
                {db:'gdb_report', tables:[{n:'rpt_daily',c:9,rows:365},{n:'rpt_kpi',c:14,rows:180}]}];
    body.innerHTML = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>数据源探索：连接后自动扫描数据库、表、字段结构，形成数据源资产清单；探索结果可一键推送至元数据目录（M09）。</span></div>'
      + '<div style="display:flex;gap:14px;flex-wrap:wrap">'
      + '<div style="flex:0 0 300px;max-width:100%">'+UI.card('库表清单', '<div class="tree">'
        + libs.map(function(lib){ return '<div class="t-node"><span class="caret open">▶</span><span class="t-ico">⛁</span><b>'+lib.db+'</b></div><div class="t-children">'
          + lib.tables.map(function(t){ return '<div class="t-node" onclick="A.dsTbl(\''+t.n+'\','+t.c+')"><span class="t-ico">▤</span>'+t.n+'<span style="margin-left:auto;color:var(--text-3);font-size:11px">'+t.c+'字段</span></div>'; }).join('')
          + '</div>'; }).join('') + '</div>')+'</div>'
      + '<div style="flex:1;min-width:300px"><div id="dsTblBox">'+UI.card('字段结构', '<div class="empty"><span class="e-ico">☚</span><p>点击左侧表查看字段结构</p></div>')+'</div></div></div>';
  }
  if(i===3){ /* 诊断 */
    body.innerHTML = UI.card('连接诊断（健康检查 / 延迟探测 / 权限验证）',
      '<button class="btn btn-primary" onclick="A.dsRunDiag()">▶ 立即执行诊断</button> <span style="color:var(--text-3);font-size:12px">对 '+UI.esc(d.host)+':'+d.port+' 执行 4 项检查</span>'
      + '<div id="diagBox" style="margin-top:12px"></div>');
  }
  if(i===4){ /* 标签 */
    body.innerHTML = UI.card('分组与标签',
      '<div class="form-grid">'
      + UI.fSelect('业务分组', 'tg_group', ['交易域','经营域','财务域','商品域','数仓','消息','公共'], {value:d.group})
      + UI.fInput('标签（逗号分隔）', 'tg_tags', {value:(d.tags||[]).join(',')})
      + '</div><button class="btn btn-primary" onclick="A.dsTagSave(\''+d.id+'\')">保存分组标签</button>'
      + '<div class="lock-tip">标签分类体系：重要性（核心/高优先）· 环境（生产/测试/开发）· 用途（联调/报表/涉密）</div>');
  }
};
A.dsPoolSave = function(id){
  var d = DB.datasources.find(function(x){return x.id===id;});
  Object.assign(d.pool, {max:+UI.val('p_max'), minIdle:+UI.val('p_min'), idle:+UI.val('p_idle'), timeout:+UI.val('p_timeout')});
  UI.toast('连接池配置已保存并生效', 'success');
};
A.dsTagSave = function(id){
  var d = DB.datasources.find(function(x){return x.id===id;});
  d.group = UI.val('tg_group');
  d.tags = UI.val('tg_tags')? UI.val('tg_tags').split(/[,，]/).map(function(s){return s.trim();}).filter(Boolean):[];
  UI.toast('分组标签已更新', 'success'); A._dsTabRender(4, d);
};
A.dsTbl = function(name, cols){
  var fs = [];
  var pool = [['id','BIGINT','主键'],['name','VARCHAR(100)','名称'],['status','TINYINT','状态'],['create_time','DATETIME','创建时间'],['amount','DECIMAL(18,2)','金额'],['user_id','BIGINT','用户ID'],['dt','DATE','分区字段'],['remark','VARCHAR(500)','备注']];
  for(var i=0;i<cols;i++) fs.push(pool[i%pool.length]);
  document.getElementById('dsTblBox').innerHTML = UI.card('字段结构 - '+name,
    UI.tbl({id:'t_dsf'+name, rowKey:'0', pageSize:10, searchKeys:['0','1','2'],
      data:function(){ return fs.map(function(f){return {c0:f[0], c1:f[1], c2:f[2]};}); },
      cols:[{t:'字段名',k:'c0',render:function(r){return '<span class="mono">'+r.c0+'</span>';}},{t:'类型',k:'c1'},{t:'注释',k:'c2'}], ops:null})
    + '<div style="margin-top:10px;display:flex;gap:8px"><button class="btn" onclick="UI.toast(\'已将 '+name+' 推送至元数据目录（M09 元数据管理）\',\'success\')">推送至元数据目录</button>'
    + '<button class="btn" onclick="App.go(\'#/sync/wizard\')">创建同步任务</button></div>');
};
A.dsExplore = function(id){ UI.toast('正在重新扫描 '+DB.datasources.find(function(x){return x.id===id;}).name+' 的库表结构 ...', 'info'); setTimeout(function(){ UI.toast('探索完成：2 个库 / 5 张表 / 53 个字段', 'success'); }, 900); };
A.dsRunDiag = function(){
  var box = document.getElementById('diagBox');
  var items = [['网络连通性','run'],['账号认证','run'],['延迟探测','run'],['权限验证(读)','run']];
  box.innerHTML = items.map(function(x){ return '<div class="checker-line run" id="dg_'+x[0]+'">◌ <b>'+x[0]+'</b><span style="margin-left:auto">检查中...</span></div>'; }).join('');
  var results = [['ok','通过','TCP 可达，路由 2 跳'],['ok','通过','用户认证成功'],['ok','通过','平均延迟 '+DB.datasources[0].latency+' ms'],['ok','通过','SELECT 权限具备']];
  items.forEach(function(x, i){
    setTimeout(function(){
      var r = results[i];
      document.getElementById('dg_'+x[0]).className = 'checker-line '+r[0];
      document.getElementById('dg_'+x[0]).innerHTML = '<span>'+(r[0]==='ok'?'✓':'✗')+'</span><b>'+x[0]+'</b><span style="margin-left:auto">'+r[1]+' · '+r[2]+'</span>';
    }, 500*(i+1));
  });
};

/* ---- 注册数据源向导（4步：类型→连接→测试→探索确认） ---- */
App.reg('#/ds/create', '注册数据源向导', function(){
  var html = UI.pageHead('注册数据源', '向导式接入：选择类型 → 填写连接 → 测试连接 → 探索确认');
  html += '<div class="card no-head"><div class="card-body" id="dsWizBody">'+A._dsWizStep(0)+'</div></div>';
  return html;
});
A._dsWizData = {step:0, type:null};
function dsWizItemsHtml(items){
  return items.map(function(x){ return '<div class="checker-line run" id="wt_'+x[0]+'">◌ <b>'+x[0]+'</b><span style="margin-left:auto">检查中...</span></div>'; }).join('');
}
A._dsWizStep = function(s){
  A._dsWizData.step = s;
  var steps = ['选择数据源类型','填写连接信息','测试连接','探索确认'];
  var inner = '';
  if(s===0){
    var groups = {};
    DB.dsTypes.forEach(function(t){ (groups[t.group]=groups[t.group]||[]).push(t); });
    inner = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>P0 收敛保障类型：万里/高斯/达梦/MySQL/Oracle 数据库、数仓引擎（Doris/Hive）、Kafka 消息队列；其余类型排后迭代。</span></div>';
    Object.keys(groups).forEach(function(g){
      inner += '<div style="font-size:12px;color:var(--text-3);margin:10px 0 6px;font-weight:600">'+g+'</div><div class="grid" style="grid-template-columns:repeat(4,1fr)">'
        + groups[g].map(function(t){
          return '<div class="stat-card hoverable" style="'+(A._dsWizData.type===t.name?'border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light)':'')+'" onclick="A._dsWizPick(\''+t.name+'\')">'
            +'<span class="type-icon" style="background:'+t.color+'">'+UI.esc(t.name.slice(0,2).toUpperCase())+'</span>'
            +'<div><b style="font-size:13px">'+t.name+'</b><div style="font-size:11px;color:var(--text-3)">默认端口 '+t.port+(t.xc?' · <span class="tag tag-xc" style="height:17px">信创</span>':'')+'</div></div></div>';
        }).join('') + '</div>';
    });
    inner += '<div style="margin-top:16px;display:flex;justify-content:flex-end"><button class="btn btn-primary" onclick="A._dsWizNext()">下一步 →</button></div>';
  }
  if(s===1){
    inner = '<div class="form-grid" style="max-width:760px">'
      + UI.fInput('数据源名称', 'w_name', {req:true, ph:'如：万里GreatDB-生产业务库'})
      + UI.fInput('主机地址', 'w_host', {req:true, ph:'IP或域名'})
      + UI.fInput('端口', 'w_port', {value:(DB.dsTypes.find(function(t){return t.name===A._dsWizData.type;})||{}).port||3306})
      + UI.fInput('数据库名', 'w_db', {})
      + UI.fInput('用户名', 'w_user', {})
      + UI.fInput('密码', 'w_pwd', {type:'password'})
      + UI.fSelect('环境', 'w_env', [{v:'生产',t:'生产'},{v:'测试',t:'测试'},{v:'开发',t:'开发'}], {value:'生产'})
      + UI.fSelect('业务分组', 'w_group', ['交易域','经营域','财务域','商品域','数仓','消息','公共'], {value:'数仓'})
      + '</div>'
      + '<div style="display:flex;justify-content:space-between"><button class="btn" onclick="A._dsWizStepRender(0)">← 上一步</button><button class="btn btn-primary" onclick="A._dsWizNext()">测试连接 →</button></div>';
  }
  if(s===2){
    inner = '<div id="wizTestBox">'+dsWizItemsHtml([['网络连通','run'],['账号认证','run'],['权限验证','run']])+'</div>'
      +'<div style="display:flex;justify-content:space-between;margin-top:14px"><button class="btn" onclick="A._dsWizStepRender(1)">← 上一步</button><button class="btn btn-primary" id="wizNextBtn" disabled onclick="A._dsWizStepRender(3)">下一步 →</button></div>';
  }
  if(s===3){
    inner = '<div class="banner banner-success"><span class="b-ico">✓</span><span>连接成功！自动探索完成：2 个库 / 5 张表 / 53 个字段，资产清单已生成并同步至元数据目录。</span></div>'
      + UI.desc([['数据源类型', A._dsWizData.type], ['名称', UI.val('w_name')||'（向导内）'], ['主机', UI.val('w_host')+':'+UI.val('w_port')], ['环境', UI.val('w_env')], ['分组', UI.val('w_group')]])
      + '<div style="display:flex;justify-content:space-between;margin-top:14px"><button class="btn" onclick="A._dsWizStepRender(1)">← 上一步</button><button class="btn btn-primary" onclick="A._dsWizFinish()">完成注册 ✓</button></div>';
  }
  return UI.steps(steps, s) + inner;
}
A._dsWizPick = function(name){ A._dsWizData.type = name; A._dsWizStepRender(0); };
A._dsWizStepRender = function(s){
  var el = document.getElementById('dsWizBody'); if(!el) return;
  el.innerHTML = A._dsWizStep(s);
  if(s===2){ /* 连接测试动画：逐项亮起，全部完成后解锁下一步 */
    var rs = [['网络连通','TCP 可达'],['账号认证','认证成功'],['权限验证','SELECT 权限具备']];
    rs.forEach(function(r, i){
      setTimeout(function(){
        var it = document.getElementById('wt_'+r[0]);
        if(it){ it.className='checker-line ok'; it.innerHTML='<span>✓</span><b>'+r[0]+'</b><span style="margin-left:auto">'+r[1]+'</span>'; }
        if(i===rs.length-1){ var b=document.getElementById('wizNextBtn'); if(b) b.disabled=false; }
      }, 600*(i+1));
    });
  }
};
A._dsWizNext = function(){
  var s = A._dsWizData.step;
  if(s===0){ if(!A._dsWizData.type){ UI.toast('请先选择数据源类型', 'warn'); return; } A._dsWizStepRender(1); }
  else if(s===1){
    if(!UI.val('w_name')||!UI.val('w_host')){ UI.toast('请填写数据源名称与主机地址', 'warn'); return; }
    A._dsWizStepRender(2);
  }
};
A._dsWizFinish = function(){
  var nid = 'DS'+String(DB.datasources.length+1).padStart(3,'0');
  DB.datasources.push({id:nid, name:UI.val('w_name')||'新建数据源', type:A._dsWizData.type, host:UI.val('w_host'), port:UI.val('w_port')||3306, db:UI.val('w_db'), user:UI.val('w_user'), pwd:'******', env:UI.val('w_env'), group:UI.val('w_group'), tags:[], pool:{max:10,minIdle:1,idle:600,timeout:30}, status:'enabled', owner:DB.user.name, createdAt:'2026-09-12 22:36', latency:8, health:'健康'});
  UI.toast('数据源注册成功（'+nid+'），资产清单已推送元数据目录', 'success');
  App.go('#/ds/list');
};

/* ---- 抽取元数据（4步：连通校验→选择库表→映射主题域/分层→入元数据目录） ---- */
A.EX_LIBS = [
  {db:'gdb_main', domain:'交易域', layer:'ODS', tables:[{n:'user_info',c:8,rows:1250000},{n:'trade_order',c:12,rows:4100000},{n:'pay_record',c:10,rows:2600000}]},
  {db:'gdb_report', domain:'经营域', layer:'ADS', tables:[{n:'rpt_daily',c:9,rows:365},{n:'rpt_kpi',c:14,rows:180}]}
];
UI._rc_ex_scope = function(v){ var b = document.getElementById('exPickBox'); if(b) b.style.display = (v==='pick'?'block':'none'); };

App.reg('#/ds/extract/:id', '抽取元数据', function(p){
  var d = DB.datasources.find(function(x){return x.id===p.id;});
  if(!d) return '<div class="empty">数据源不存在</div>';
  A._exDs = p.id;
  var html = UI.pageHead('<a onclick="App.go(\'#/ds/list\')">← 数据源管理</a> / 抽取元数据 - '+UI.esc(d.name),
    d.id+' · '+UI.esc(d.type)+' · <span class="mono">'+UI.esc(d.host)+':'+d.port+'</span> · '+(d.db? UI.esc(d.db):'-'),
    st(d.status));
  html += '<div class="card no-head"><div class="card-body" style="padding-bottom:14px">'
    + '<div id="exSteps">'+UI.steps(['连通校验','选择库表','映射主题域/分层','入元数据目录'], 0)+'</div>'
    + '<div class="lock-tip" style="margin-top:0">流程图例：① 连通校验（复用连接诊断：网络/认证/权限）→ ② 选择库表（全库扫描或指定表多选）→ ③ 映射主题域/分层（按命名规则自动归类 ODS/DWD… 与业务域）→ ④ 入元数据目录（技术+业务元数据入库，与采集任务联动）</div>'
    + '</div></div>';
  var tblOpts = [];
  A.EX_LIBS.forEach(function(lib){ lib.tables.forEach(function(t){ tblOpts.push({v:lib.db+'.'+t.n, t:lib.db+'.'+t.n+'（'+t.c+' 字段 · '+fmt(t.rows)+' 行）'}); }); });
  html += '<div style="display:flex;gap:16px;align-items:flex-start">'
    + '<div style="flex:0 0 430px;max-width:100%">'+UI.card('抽取配置',
      UI.fRadio('抽取范围', 'ex_scope', [{v:'all',t:'全库（'+tblOpts.length+' 张表）'},{v:'pick',t:'指定表（多选）'}], 'all')
      + '<div id="exPickBox" style="display:none">'+UI.fCheckGroup('选择表', 'ex_tbls', tblOpts, [], '勾选需抽取的表；未勾选时无法开始抽取')+'</div>'
      + UI.fRadio('采集方式', 'ex_mode', [{v:'inc',t:'增量采集'},{v:'full',t:'全量采集'}], 'inc', '增量：按变更位点/时间戳抽取；全量：整表重扫')
      + '<div class="form-grid">'
      + UI.fSelect('采集并发', 'ex_conc', [{v:'2',t:'2 并发（低负载）'},{v:'4',t:'4 并发（推荐）'},{v:'8',t:'8 并发（高负载）'}], {value:'4'})
      + '</div>'
      + UI.fSwitch('采集字段注释', 'ex_cmt', true, '字段名/类型/注释/主键等技术元数据')
      + UI.fSwitch('采集样例值', 'ex_sample', true, '每表抽样前 10 行，敏感字段自动脱敏')
      + '<div style="display:flex;gap:8px;margin-top:4px"><button class="btn btn-primary" onclick="A.exStart()">▶ 开始抽取</button>'
      + '<button class="btn" onclick="A.exPreview()">刷新预览</button></div>')+'</div>'
    + '<div style="flex:1;min-width:0">'+UI.card('抽取预览',
      '<div id="exPrevBody"></div><div id="exRunBox" style="margin-top:12px"></div>')+'</div>'
    + '</div>';
  App.onAfterRender(function(mm){ if(mm.path.indexOf('#/ds/extract/')===0) A.exPreview(); });
  return html;
});
A._exPick = function(){
  var scope = UI.radioVal('ex_scope','all');
  var picked = UI.checkVals('ck-ex_tbls');
  return A.EX_LIBS.map(function(lib){
    var ts = scope==='pick'? lib.tables.filter(function(t){ return picked.indexOf(lib.db+'.'+t.n)>=0; }) : lib.tables;
    return {db:lib.db, domain:lib.domain, layer:lib.layer, tables:ts};
  }).filter(function(l){ return l.tables.length; });
};
A._exEstimate = function(fields, mode, conc){
  var sec = Math.max(8, Math.round((fields*12 + (mode==='full'? 45:15)) / (conc||4)));
  return sec>=90? (sec/60).toFixed(1)+' 分钟' : sec+' 秒';
};
A.exPreview = function(){
  var box = document.getElementById('exPrevBody'); if(!box) return;
  var libs = A._exPick(), nT = 0, nF = 0;
  libs.forEach(function(l){ l.tables.forEach(function(t){ nT++; nF += t.c; }); });
  var mode = UI.radioVal('ex_mode','inc');
  var conc = +UI.val('ex_conc') || 4;
  box.innerHTML = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">'
    + '<div class="stat-card" style="flex:1;min-width:104px;padding:10px"><div><div class="stat-num" style="font-size:19px">'+libs.length+'</div><div class="stat-label">库</div></div></div>'
    + '<div class="stat-card" style="flex:1;min-width:104px;padding:10px"><div><div class="stat-num" style="font-size:19px">'+nT+'</div><div class="stat-label">表</div></div></div>'
    + '<div class="stat-card" style="flex:1;min-width:104px;padding:10px"><div><div class="stat-num" style="font-size:19px">'+nF+'</div><div class="stat-label">字段</div></div></div>'
    + '<div class="stat-card" style="flex:1;min-width:120px;padding:10px"><div><div class="stat-num" style="font-size:19px">'+A._exEstimate(nF, mode, conc)+'</div><div class="stat-label">预计时长（'+conc+'并发·'+(mode==='inc'?'增量':'全量')+'）</div></div></div></div>'
    + '<div class="tree">'
    + libs.map(function(l){
        return '<div class="t-node"><span class="caret open">▶</span><span class="t-ico">⛁</span><b>'+l.db+'</b><span style="margin-left:auto;color:var(--text-3);font-size:11px">'+l.tables.length+' 表 · 拟映射 '+l.layer+'/'+l.domain+'</span></div>'
          + '<div class="t-children">'+ l.tables.map(function(t){
              return '<div class="t-node"><span class="t-ico">▤</span>'+t.n+'<span style="margin-left:auto;color:var(--text-3);font-size:11px">'+t.c+' 字段 · '+fmt(t.rows)+' 行</span></div>';
            }).join('') +'</div>';
      }).join('')
    + (libs.length? '' : '<div class="empty" style="padding:14px"><p>尚未选择表，请在左侧勾选</p></div>')
    + '</div>'
    + '<div class="lock-tip">预览为模拟扫描结果：实际以连通校验后的源端结构为准；「字段注释/样例值」开关影响入库内容。</div>';
};
A._exStepsRender = function(cur){
  var el = document.getElementById('exSteps');
  if(el) el.innerHTML = UI.steps(['连通校验','选择库表','映射主题域/分层','入元数据目录'], cur);
};
A.exStart = function(){
  if(A._exRunning) return;
  var d = DB.datasources.find(function(x){return x.id===A._exDs;});
  if(!d) return;
  var scope = UI.radioVal('ex_scope','all');
  var picked = UI.checkVals('ck-ex_tbls');
  if(scope==='pick' && !picked.length){ UI.toast('抽取范围为「指定表」，请至少勾选 1 张表', 'warn'); return; }
  var libs = A._exPick(), nT = 0, nF = 0;
  libs.forEach(function(l){ l.tables.forEach(function(t){ nT++; nF += t.c; }); });
  var conc = UI.val('ex_conc') || '4';
  var cmt = UI.switchOn('ex_cmt'), smp = UI.switchOn('ex_sample');
  var layers = [], domains = [];
  libs.forEach(function(l){ if(layers.indexOf(l.layer)<0) layers.push(l.layer); if(domains.indexOf(l.domain)<0) domains.push(l.domain); });
  A._exRunning = true;
  A._exStepsRender(0);
  var logs = [
    'TCP 连通 · 账号认证通过 · 延迟 '+d.latency+' ms · SELECT 权限具备',
    (scope==='all'? '全库扫描：'+libs.length+' 个库 / '+nT+' 张表 / '+nF+' 个字段' : '指定表抽取：'+nT+' 张（'+picked.slice(0,2).join('、')+(picked.length>2?' 等':'')+'）'),
    '命名规则映射：分层 '+(layers.join('/')||'ODS')+' · 主题域 '+(domains.join('/')||'公共'),
    '元数据入库：库表结构'+(cmt?' + 字段注释':'')+(smp?' + 样例值':'')+'（'+conc+' 并发'+(UI.radioVal('ex_mode','inc')==='inc'?'·增量':'·全量')+'）'
  ];
  var box = document.getElementById('exRunBox');
  if(box) box.innerHTML = logs.map(function(x, i){
    return '<div class="checker-line run" id="exlg_'+i+'">◌ <b>步骤 '+(i+1)+'</b><span style="margin-left:auto">执行中...</span></div>';
  }).join('');
  logs.forEach(function(x, i){
    setTimeout(function(){
      var it = document.getElementById('exlg_'+i);
      if(it){ it.className = 'checker-line ok'; it.innerHTML = '<span>✓</span><b>步骤 '+(i+1)+'</b><div style="flex:1;margin-left:6px;font-size:11.5px;color:var(--text-2)">'+UI.esc(x)+'</div>'; }
      A._exStepsRender(i+1);
      if(i===logs.length-1) A._exDone(d, nT, scope, libs, conc);
    }, 800*(i+1));
  });
};
A._exDone = function(d, nT, scope, libs, conc){
  A._exRunning = false;
  var scopeTxt = scope==='all'? UI.esc(d.name)+'：全库' : UI.esc(d.name)+'：'+libs.reduce(function(s,l){return s+l.tables.length;},0)+' 张指定表';
  var name = '抽取元数据 - '+d.name;
  var t = DB.collectTasks.filter(function(x){return x.name===name;})[0];
  if(t){ t.scope = scopeTxt; t.lastRun = now+' 23:0'+Math.floor(Math.random()*10); t.lastResult = 'success'; t.tables = (t.tables||0)+nT; }
  else DB.collectTasks.push({id:'MC'+String(DB.collectTasks.length+1).padStart(3,'0'), name:name, scope:scopeTxt, type:'触发式', cron:'-', lastRun:now+' 23:05', lastResult:'success', tables:nT, status:'enabled'});
  var box = document.getElementById('exRunBox');
  if(box) box.innerHTML = '<div class="banner banner-success" style="margin-bottom:10px"><span class="b-ico">✓</span><span>抽取完成：<b>'+nT+'</b> 张表元数据已入库（目录/血缘已更新），并已在采集任务列表生成记录。</span></div>'
    + '<div style="display:flex;gap:8px"><button class="btn btn-primary" onclick="App.go(\'#/meta/catalog\')">前往元数据目录</button>'
    + '<button class="btn" onclick="App.go(\'#/meta/collect\')">查看采集任务</button></div>';
  UI.toast('元数据已入库，可在元数据目录查看', 'success');
};
})();
