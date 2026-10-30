/* ============================================================
   M12 参数配置（全局参数/内置时间参数/环境参数组/引用检测与预览）
   闭环：定义参数 → 引用检测 → 执行时按环境注入 → 预览解析结果
   ============================================================ */
(function(){
/* ---- 全局参数 ---- */
App.reg('#/param/global', '全局参数', function(){
  var html = UI.pageHead('全局参数',
    '跨任务共享的键值参数：敏感参数加密存储（界面脱敏），执行时按当前环境注入',
    '<button class="btn btn-primary" onclick="A.gpCreate()">+ 新建参数</button>');
  html += UI.card('参数列表', UI.tbl({
    id:'t_gp', rowKey:'id', pageSize:8, selectable:true, searchKeys:['id','name','desc'], searchPh:'搜索参数',
    filters:[{k:'encrypt', label:'加密', options:[{v:true,t:'加密'},{v:false,t:'明文'}]}],
    data:function(){ return DB.globalParams; },
    cols:[
      {t:'参数名', k:'name', sortable:true, render:function(r){return '<span class="mono"><b>${'+r.name+'}</b></span><div style="font-size:11px;color:var(--text-3)">'+r.id+'</div>';}},
      {t:'值', render:function(r){return r.encrypt? '<span class="mono">******</span> <span class="tag tag-orange" style="height:16px;font-size:10px">已加密</span>' : '<span class="mono">'+UI.esc(r.value)+'</span>';}},
      {t:'类型', k:'type'},
      {t:'说明', k:'desc'},
      {t:'更新日期', k:'updatedAt'}
    ],
    ops:function(r){
      return '<a onclick="A.gpEdit(\''+r.id+'\')">编辑</a>'
        +'<a onclick="A.gpRef(\''+r.name+'\')">引用任务</a>'
        +'<a class="danger" onclick="A.gpDel(\''+r.id+'\')">删除</a>';
    }}));
  return html;
});
A.gpFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('参数名', 'gp_name', {value:d.name, req:true, ph:'如：doris_host'})
    + UI.fInput('值', 'gp_value', {value:d.encrypt?'******':d.value, full:true})
    + UI.fSelect('类型', 'gp_type', ['文本','数值','布尔','JSON'], {value:d.type||'文本'})
    + UI.fSwitch('敏感加密存储（界面脱敏）', 'gp_enc', !!d.encrypt, '加密后值以 ****** 展示，执行时解密注入')
    + UI.fTextarea('说明', 'gp_desc', {value:d.desc, rows:2, full:true})
    + '</div>';
};
A.gpCreate = function(){ UI.drawer({title:'新建全局参数', w:'w-lg', body:A.gpFormFields({}), onOk:function(){
  var name = UI.val('gp_name');
  if(!name){ UI.toast('请填写参数名', 'warn'); return false; }
  if(DB.globalParams.some(function(p){return p.name===name;})){ UI.toast('参数名已存在', 'error'); return false; }
  var enc = UI.switchOn('gp_enc');
  DB.globalParams.push({id:'GP0'+(DB.globalParams.length+1), name:name, value:enc?'******':UI.val('gp_value'), type:UI.val('gp_type'), encrypt:enc, desc:UI.val('gp_desc'), env:DB.env, updatedAt:now});
  UI.toast('参数已创建：脚本/SQL 中通过 ${'+name+'} 引用', 'success');}}); };
A.gpEdit = function(id){ var d = DB.globalParams.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑参数 - '+d.name, w:'w-lg', body:A.gpFormFields(d), onOk:function(){
    var enc = UI.switchOn('gp_enc');
    Object.assign(d, {name:UI.val('gp_name'), value:UI.val('gp_value')==='******'? d.value : UI.val('gp_value'), type:UI.val('gp_type'), encrypt:enc, desc:UI.val('gp_desc'), updatedAt:now});
    UI.toast('参数已保存', 'success');}}); };
A.gpRef = function(name){
  UI.modal({title:'参数引用 - ${'+name+'}', w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.tbl({id:'t_gpref', rowKey:'id', pageSize:6, searchKeys:['n'], data:function(){
      var rows = [];
      DB.etlTasks.forEach(function(t){ if(t.sql && t.sql.indexOf('${'+name+'}')>=0) rows.push({id:t.id, n:t.id+' '+t.name+'（SQL任务）'}); });
      DB.scripts.forEach(function(s){ if(s.code.indexOf('${'+name+'}')>=0) rows.push({id:s.id, n:s.id+' '+s.name+'（脚本）'}); });
      return rows;},
      cols:[{t:'引用位置', k:'n'},{t:'操作', render:function(r){return '<a onclick="App.go(\'#/param/tools\')">引用检测</a>';}}], ops:null})});
};
A.gpDel = function(id){
  var d = DB.globalParams.find(function(x){return x.id===id;});
  UI.confirm({title:'删除参数', danger:true, msg:'确认删除参数「${'+d.name+'}」？', detail:'引用该参数的任务执行时将报「参数未定义」错误，请先确认无引用。', onOk:function(){
    var i = DB.globalParams.findIndex(function(x){return x.id===id;});
    DB.globalParams.splice(i,1); UI.toast('参数已删除', 'info'); App.resolve();
  }});
};

/* ---- 内置时间参数 ---- */
App.reg('#/param/builtin', '内置时间参数', function(){
  var html = UI.pageHead('内置时间参数', '调度内置时间变量：无需定义直接在 SQL/脚本中引用，按业务日期（T-1）解析');
  html += UI.card('内置参数一览（以业务日期 2026-09-11 为例）', UI.tbl({
    id:'t_bp', rowKey:'name', pageSize:12, searchKeys:['name','desc'], searchPh:'搜索参数',
    data:function(){ return DB.builtinParams; },
    cols:[
      {t:'参数', k:'name', render:function(r){return '<span class="mono"><b>'+r.name+'</b></span>';}},
      {t:'说明', k:'desc'},
      {t:'解析示例', k:'eg', render:function(r){return '<span class="mono" style="color:var(--success)">'+r.eg+'</span>';}}
    ],
    ops:function(r){ return '<a onclick="A.bpTry(\''+r.name+'\')">试算</a>'; }}));
  return html;
});
A.bpTry = function(name){
  var p = DB.builtinParams.find(function(x){return x.name===name;});
  UI.toast('试算 '+name+' → '+p.eg+'（基于业务日期 T-1）', 'info');
};

/* ---- 环境参数组 ---- */
App.reg('#/param/env', '环境参数组', function(){
  var html = UI.pageHead('环境参数组',
    '同一套任务跨环境（开发/联调/生产）运行：环境参数组覆盖同名全局参数，切换顶栏环境即生效',
    '<button class="btn" onclick="UI.toast(\'环境切换请使用顶栏 DEV / STAGING / PROD 开关\',\'info\')">切换环境</button>');
  html += UI.card('参数组', UI.tbl({
    id:'t_eg', rowKey:'name', pageSize:8, searchKeys:['name','desc'], data:function(){ return DB.envGroups; },
    cols:[
      {t:'环境', k:'name', render:function(r){return tag(r.name.toUpperCase(), r.name==='prod'?'red':r.name==='staging'?'orange':'cyan');}},
      {t:'说明', k:'desc'},
      {t:'参数数', k:'cnt'},
      {t:'默认数据源', k:'ds'},
      {t:'参数预览', k:'params', render:function(r){return '<span class="mono" style="font-size:11px">'+UI.esc(r.params)+'</span>';}}
    ],
    ops:function(r){ return '<a onclick="A.egView(\''+r.name+'\')">查看差异</a>'; }}));
  return html;
});
A.egView = function(name){
  var g = DB.envGroups.find(function(x){return x.name===name;});
  UI.modal({title:'环境参数组 - '+name.toUpperCase(), w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.desc([['环境', g.desc],['参数数', g.cnt],['默认数据源', g.ds],['参数', '<span class="mono" style="font-size:11.5px">'+UI.esc(g.params)+'</span>']])
    + '<div class="lock-tip">同名参数按「节点参数 > 工作流变量 > 环境组 > 全局」优先级解析。</div>'});
};

/* ---- 引用检测与预览 ---- */
App.reg('#/param/tools', '引用检测与预览', function(){
  var html = UI.pageHead('引用检测与参数预览',
    '发布前校验：扫描 SQL/脚本中的 ${参数} 引用是否已定义；并按解析优先级预览最终值',
    '<button class="btn btn-primary" onclick="A.ptScan()">▶ 重新扫描</button>');
  html += '<div class="grid" style="grid-template-columns:1.4fr 1fr;gap:16px;align-items:flex-start">';
  html += UI.card('引用检测结果',
    UI.tbl({id:'t_rc', rowKey:'file', pageSize:8, searchKeys:['file'], data:function(){ return DB.refCheckResult; },
      cols:[
        {t:'文件/任务', k:'file'},
        {t:'引用参数', render:function(r){return r.refs.map(function(x){return '<span class="mono tag tag-outline" style="margin:1px 3px 1px 0">'+x+'</span>';}).join('');}},
        {t:'结果', render:function(r){return st(r.result==='pass'?'pass':'reject');}},
        {t:'说明', k:'detail', render:function(r){return '<span style="font-size:11.5px">'+UI.esc(r.detail)+'</span>';}}
      ],
      ops:function(r){ return r.result==='fail'? '<a onclick="A.ptFix(\''+UI.esc(r.file)+'\')">去修复</a>':'<a onclick="UI.toast(\''+UI.esc(r.detail)+'\',\'info\')">详情</a>'; }}));
  html += UI.card('参数解析预览（优先级：节点 > 工作流 > 环境组 > 全局）',
    UI.tbl({id:'t_pp', rowKey:'name', pageSize:8, searchKeys:['name'], data:function(){ return DB.paramPreview; },
      cols:[{t:'参数', k:'name', render:function(r){return '<span class="mono">${'+r.name+'}</span>'}},
            {t:'作用域', k:'scope'},
            {t:'解析值', k:'value', render:function(r){return '<span class="mono" style="color:var(--success)">'+UI.esc(r.value)+'</span>';}}], ops:null})
    + '<div class="banner banner-warn" style="margin-top:12px"><span class="b-ico">⚠</span><span>存在 1 个未定义引用（${src_schema}），请在「全局参数」新增或修正拼写，否则任务执行将失败。</span></div>'
    + '<button class="btn btn-primary" onclick="App.go(\'#/param/global\')">去参数管理修复</button>');
  html += '</div>';
  return html;
});
A.ptScan = function(){
  UI.toast('正在扫描 ETL 任务 / 脚本中的参数引用...', 'info');
  setTimeout(function(){ UI.toast('扫描完成：3 个文件 / 5 个参数引用 / 1 个未定义', 'warn'); App.resolve(); }, 900);
};
A.ptFix = function(file){
  UI.toast('已定位 '+file+'：${src_schema} 未定义，请在全局参数中新增', 'warn');
  App.go('#/param/global');
};
})();
