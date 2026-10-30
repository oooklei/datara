/* ============================================================
   M11 数据开发IDE（P0：在线编辑/多数据源/预览/导出/树形目录/执行历史/函数参考）
   编辑闭环：可编辑 → 运行测试 → 语法解析 → 验证(血缘/参数/权限) → AI优化 → 发布ETL
   执行计划分析排后（P0范围外）
   ============================================================ */
(function(){
App.reg('#/ide', 'SQL开发IDE', function(){
  var ds = DB.datasources.filter(function(d){return d.type!=='Kafka';});
  var html = UI.pageHead('数据开发IDE',
    '浏览器内SQL开发环境：多数据源连接 / 智能补全 / 运行测试 / 语法解析 / 验证（血缘·参数·权限）/ AI优化 / 发布为ETL任务（执行计划分析排后迭代）',
    '<span class="tag tag-cyan tag-lg">数据源：<select class="sel" style="height:24px;border:none;background:transparent;font-weight:600" onchange="A.ideSwitchDs(this.value)">'
    + ds.map(function(d){ return '<option value="'+d.id+'" '+(d.id==='DS006'?'selected':'')+'>'+d.name+'</option>'; }).join('')
    +'</select></span>'
    +'<button class="btn" onclick="A.ideFmt()">格式化</button>'
    +'<button class="btn btn-primary" onclick="A.ideRun()">▶ 执行 (Ctrl+Enter)</button>');
  html += '<div style="display:flex;gap:14px;align-items:stretch">'
    /* 左侧树 */
    +'<div class="card no-head" style="width:250px;flex-shrink:0"><div class="card-body" style="padding:8px">'
    +'<div style="display:flex;gap:6px;margin-bottom:6px"><input class="inp" placeholder="搜索表/字段" style="height:26px;font-size:12px" oninput="A.ideTreeFilter(this.value)"></div>'
    +'<div class="tree" id="ideTree">'+A._ideTree('')+'</div>'
    +'</div></div>'
    /* 右侧编辑+结果 */
    +'<div style="flex:1;min-width:0">'
    +'<div style="display:flex;gap:4px;align-items:flex-end;flex-wrap:wrap">'+DB.ideTabs.map(function(t, i){
      return '<span class="file-tab'+(i===DB.ideActive?' on':'')+'" onclick="A.ideTab('+i+')">'+UI.esc(t.name)+'<span class="ft-x" onclick="event.stopPropagation();A.ideCloseTab('+i+')">✕</span></span>';
    }).join('')
    +'<span class="file-tab" style="border-style:dashed;color:var(--text-3)" onclick="A.ideAddTab()">＋ 新查询</span></div>'
    +'<div class="card no-head" style="margin-bottom:12px"><div class="card-body" style="padding:0">'
    +'<div class="editor-toolbar"><span style="font-size:12px;color:var(--text-3)">Doris-分析集群 / dw_olap · 自动补全：输入表名后按 <span class="hint-kbd">.</span> 提示字段</span><span style="flex:1"></span>'
    +'<button class="btn btn-sm" onclick="A.ideFmt()">格式化</button>'
    +'<button class="btn btn-sm" onclick="A.ideSave()">保存</button>'
    +'<button class="btn btn-primary btn-sm" onclick="A.ideRun()">▶ 运行测试</button>'
    +'<button class="btn btn-sm" onclick="A.ideParse()">✓ 语法解析</button>'
    +'<button class="btn btn-sm" onclick="A.ideVerify()">⊘ 验证</button>'
    +'<button class="btn btn-sm" onclick="A.ideAiFmt()">✦ AI 优化</button>'
    +'<button class="btn btn-primary btn-sm" onclick="A.idePublish()">发布</button></div>'
    +'<textarea class="editor-area" id="ideEditor" style="min-height:150px" onkeydown="if((event.ctrlKey||event.metaKey)&&event.key===\'Enter\'){A.ideRun()}" oninput="A.ideInput(this)">'+UI.esc(DB.ideTabs[DB.ideActive].sql)+'</textarea></div></div>'
    + UI.tabs('ideTab', [{label:'结果',render:1},{label:'执行历史',cnt:DB.ideHistory.length,render:1},{label:'收藏SQL',render:1},{label:'解析',render:1},{label:'验证',render:1},{label:'函数参考',render:1}], 0)
    +'<div id="ideTabBody"></div>'
    +'</div></div>';
  UI._tabCb['ideTab'] = function(i){ A._ideTab(i); };
  App.onAfterRender(function(mm){ if(mm.path==='#/ide') A._ideTab(0); });
  return html;
});
DB.ideTabs = [{name:'查询1', sql:"SELECT channel,\n       pay_user_cnt,\n       pay_order_cnt,\n       pay_amount_sum\nFROM dws_pay_summary_daily\nWHERE dt = '${biz_date}'\nORDER BY pay_amount_sum DESC;"}];
DB.ideActive = 0;

A._ideTree = function(q){
  var tree = [
    {icon:'⛁', label:'dw_olap（Doris）', children:[
      {icon:'▤', label:'dws_pay_summary_daily', children:[
        {icon:'·', label:'stat_date DATE'},{icon:'·', label:'channel VARCHAR'},{icon:'·', label:'pay_user_cnt BIGINT'},{icon:'·', label:'pay_order_cnt BIGINT'},{icon:'·', label:'pay_amount_sum DECIMAL'}
      ]},
      {icon:'▤', label:'dwd_order_pay_detail', children:[{icon:'·', label:'pay_id BIGINT'},{icon:'·', label:'pay_amount DECIMAL'},{icon:'·', label:'dt DATE'}]},
      {icon:'▤', label:'ads_kpi_report', children:[{icon:'·', label:'stat_date DATE'},{icon:'·', label:'gmv DECIMAL'}]},
      {icon:'▤', label:'ods_gdb_biz_user_info', children:[{icon:'·', label:'user_id BIGINT'},{icon:'·', label:'user_name VARCHAR'}]}
    ]}
  ];
  function r(list){
    return list.map(function(n){
      if(q && n.label.toLowerCase().indexOf(q.toLowerCase())<0 && !(n.children&&n.children.some(function(c){return c.label.toLowerCase().indexOf(q.toLowerCase())>=0;}))) return '';
      var kids = n.children? '<div class="t-children">'+r(n.children)+'</div>' : '';
      return '<div class="t-node" onclick="A.ideTreeClick(this,\''+UI.esc(n.label).replace(/'/g,'')+'\')"><span class="caret'+(n.children?' open':'')+'">▶</span><span class="t-ico">'+n.icon+'</span><span>'+UI.esc(n.label)+'</span></div>'+kids;
    }).join('');
  }
  return r(tree);
};
A.ideTreeFilter = function(q){ document.getElementById('ideTree').innerHTML = A._ideTree(q); };
A.ideTreeClick = function(el, label){
  el.parentNode.querySelectorAll('.t-node').forEach(function(n){n.classList.remove('on');});
  el.classList.add('on');
  if(label.indexOf(' ') < 0){ /* 表名 */
    var ed = document.getElementById('ideEditor');
    ed.value += (ed.value.endsWith(' ')||ed.value==='')? label : ' '+label;
    DB.ideTabs[DB.ideActive].sql = ed.value;
    UI.toast('已插入表名 '+label+'，双击可展开字段', 'info');
  }
};
A.ideSwitchDs = function(id){
  var d = DB.datasources.find(function(x){return x.id===id;});
  UI.toast('已切换数据源：'+d.name+'（'+d.type+'，'+(d.type==='达梦 DM8'||d.type==='万里 GreatDB'||d.type==='华为 GaussDB'?'信创':'通用')+'）', 'info');
};
A.ideTab = function(i){ DB.ideActive = i; App.resolve(); };
A.ideCloseTab = function(i){
  DB.ideTabs.splice(i,1);
  if(!DB.ideTabs.length) DB.ideTabs.push({name:'查询1', sql:'SELECT 1;'});
  DB.ideActive = Math.max(0, DB.ideActive>=i? DB.ideActive-1 : DB.ideActive);
  App.resolve();
};
A.ideAddTab = function(){
  DB.ideTabs.push({name:'查询'+(DB.ideTabs.length+1), sql:''});
  DB.ideActive = DB.ideTabs.length-1;
  App.resolve();
};
A.ideInput = function(ed){ DB.ideTabs[DB.ideActive].sql = ed.value; A.ideComplete(ed); };
A.ideFmt = function(){
  var ed = document.getElementById('ideEditor'); if(!ed) return;
  ed.value = ed.value.replace(/\s+/g,' ').replace(/\s*(SELECT|FROM|WHERE|GROUP BY|ORDER BY|INSERT INTO|VALUES|AND|OR|ON|JOIN|LEFT JOIN)\s*/gi,'\n$1 ').trim();
  DB.ideTabs[DB.ideActive].sql = ed.value;
  UI.toast('SQL已格式化', 'success');
};
A.ideSave = function(){ var ed = document.getElementById('ideEditor'); if(ed) DB.ideTabs[DB.ideActive].sql = ed.value; UI.toast('已保存至「我的SQL草稿」', 'success'); };

/* ---- ▶ 运行测试（执行 + 记录历史，真实联动） ---- */
A.ideRun = function(){
  var ed = document.getElementById('ideEditor');
  var sql = ed? ed.value : DB.ideTabs[DB.ideActive].sql;
  DB.ideTabs[DB.ideActive].sql = sql;
  if(!sql.trim()){ UI.toast('当前查询为空，请先编写SQL', 'warn'); return; }
  UI.toast('执行中 '+DB.datasources[5].name+' ...', 'info');
  setTimeout(function(){
    A._ideResult = {rows:2, dur:'0.31s'};
    DB.ideHistory.unshift({id:'H'+String(DB.ideHistory.length+1).padStart(3,'0'), ds:'DS006', sql:sql, rows:2, dur:'0.31s', time:now+' 23:40', star:false});
    A._ideTab(0);
    UI.toast('运行测试通过：2 行，耗时 0.31s（已记录执行历史）', 'success');
  }, 700);
};

/* ---- ✓ 语法解析（模拟解析器：关键字配对/括号计数/分号结尾/血缘抽取） ---- */
A.ideParse = function(){
  var ed = document.getElementById('ideEditor'); if(!ed) return;
  DB.ideTabs[DB.ideActive].sql = ed.value;
  A._ideParse = A._parseSql(ed.value);
  UI.switchTab('ideTab', 3, 1, 1);
  var p = A._ideParse;
  UI.toast(p.ok? '语法解析通过：'+p.stmts.length+' 条语句，未发现问题' : '解析完成：发现 '+p.problems.length+' 个问题，详见「解析」Tab', p.ok?'success':'warn');
};
A._blankComments = function(sql){
  /* 注释与字符串内容按同长度置空，保持行列号与原文对齐 */
  return sql.replace(/--[^\n]*/g, function(m){ return m.replace(/[^\n]/g,' '); })
            .replace(/\/\*[\s\S]*?\*\//g, function(m){ return m.replace(/[^\n]/g,' '); })
            .replace(/'(?:[^']|'')*'/g, function(m){ return "'" + m.slice(1,-1).replace(/[^\n]/g,' ') + "'"; });
};
A._splitTop = function(s){
  var out=[], cur='', d=0, i, c;
  for(i=0;i<s.length;i++){
    c = s.charAt(i);
    if(c==='(') d++;
    if(c===')') d--;
    if(c===',' && d===0){ out.push(cur); cur=''; } else cur+=c;
  }
  if(cur.trim()) out.push(cur);
  return out;
};
A._parseSql = function(sql){
  var problems = [], stmts = [];
  if(!sql || !sql.trim()) return {ok:false, stmts:[], tables:[], params:[], fields:0, problems:[{line:1, msg:'编辑器为空，未检测到有效SQL语句'}]};
  var blank = A._blankComments(sql);
  /* 1. 括号计数（跨行） */
  var ls = blank.split('\n'), depth = 0, openLine = 0, i;
  for(i=0;i<ls.length;i++){
    var ops = (ls[i].match(/\(/g)||[]).length, cls = (ls[i].match(/\)/g)||[]).length;
    if(depth===0 && ops>cls) openLine = i+1;
    depth += ops - cls;
    if(depth < 0){ problems.push({line:i+1, msg:'括号不匹配：多余的右括号 ")"'}); depth = 0; }
  }
  if(depth > 0) problems.push({line:openLine||1, msg:'括号不匹配：第 '+openLine+' 行的 "(" 未闭合（缺少 '+depth+' 个 ")"）'});
  /* 2. 按分号切分语句（忽略字符串/注释内的分号，blank 与 sql 等长对齐） */
  var cur = '', start = 1, line = 1, cutFrom = 0;
  stmts = [];
  for(i=0;i<blank.length;i++){
    var ch2 = blank.charAt(i);
    if(ch2==='\n') line++;
    if(ch2===';'){
      stmts.push({text:sql.slice(cutFrom, i+1), start:start, end:line});
      cutFrom = i+1; start = line; cur='';
      continue;
    }
    cur += ch2;
  }
  if(cur.trim()) { problems.push({line:start, msg:'结尾语句未以分号 ; 结尾'}); stmts.push({text:sql.slice(cutFrom), start:start, end:line}); }
  if(!stmts.length) problems.push({line:1, msg:'未检测到有效SQL语句'});
  /* 3. 逐语句：关键字配对 / 表 / 字段 / 参数抽取 */
  var allTabs = [], allParams = [], fieldCnt = 0;
  stmts.forEach(function(st){
    var body0 = A._blankComments(st.text).replace(/\s+/g,' ').trim();
    var up = body0.toUpperCase();
    var type = up.indexOf('INSERT')===0? 'INSERT' : up.indexOf('CREATE')===0? 'CREATE' : up.indexOf('WITH')===0? 'WITH(CTE)' : up.indexOf('SELECT')===0? 'SELECT' : 'SQL';
    var clauses = ['SELECT','FROM','WHERE','GROUP BY','HAVING','ORDER BY','LIMIT'].filter(function(k){ return up.indexOf(k)>=0; });
    if((type==='SELECT'||type==='INSERT'||type==='WITH(CTE)') && up.indexOf('SELECT')<0)
      problems.push({line:st.start, msg:'语句'+(type==='INSERT'?'（INSERT）':'')+'缺少 SELECT 关键字'});
    else if(up.indexOf('SELECT')>=0 && up.indexOf('FROM')<0 && type!=='CREATE'){
      /* 常量查询（SELECT 1 / SELECT CURRENT_DATE）不要求 FROM */
      var sel = body0.slice(up.indexOf('SELECT')+6).replace(/;+\s*$/,'').trim();
      if(!/^[\d'".,+\-*/()%\s]*$/.test(sel) && !/CURRENT_DATE|CURRENT_TIMESTAMP/i.test(sel))
        problems.push({line:st.start, msg:'SELECT 语句缺少 FROM 子句'});
    }
    /* 表引用 */
    var tabs = [], re = /\b(?:FROM|JOIN|INTO|OVERWRITE\s+TABLE|CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?|UPDATE)\s+([a-zA-Z_][\w$.]*)/gi, m;
    while((m = re.exec(body0))){ if(tabs.indexOf(m[1])<0) tabs.push(m[1]); if(allTabs.indexOf(m[1])<0) allTabs.push(m[1]); }
    /* 字段引用（SELECT 列，按顶层逗号切分） */
    var fields = [];
    var fm = body0.match(/\bSELECT\b([\s\S]*?)\bFROM\b/i);
    if(fm){ fields = A._splitTop(fm[1].replace(/\n/g,' ')).map(function(f){return f.trim();}).filter(function(f){return f && f.toUpperCase()!=='DISTINCT';}); fieldCnt += fields.length; }
    /* 参数引用 */
    var ps = [], pre = /\$\{(\w+)\}/g;
    while((m = pre.exec(st.text))){ if(ps.indexOf(m[1])<0) ps.push(m[1]); if(allParams.indexOf(m[1])<0) allParams.push(m[1]); }
    st.type = type; st.clauses = clauses; st.tables = tabs; st.fields = fields; st.params = ps;
  });
  return {ok:problems.length===0, stmts:stmts, tables:allTabs, params:allParams, fields:fieldCnt, problems:problems};
};

/* ---- ⊘ 验证（表血缘解析 + 参数引用检测 + 权限校验，三项打勾动画） ---- */
A.ideVerify = function(){
  var ed = document.getElementById('ideEditor'); if(!ed) return;
  var sql = ed.value;
  DB.ideTabs[DB.ideActive].sql = sql;
  if(!sql.trim()){ UI.toast('当前查询为空，无法验证', 'warn'); return; }
  var p = A._parseSql(sql);
  A._ideParse = p; /* 验证联动解析结果 */
  A._ideVerify = {done:false, time:now+' 23:45', checks:[
    {name:'表血缘解析', ok:false, detail:'解析中：扫描表引用...'},
    {name:'参数引用检测', ok:false, detail:'解析中：扫描 ${} 占位符...'},
    {name:'权限校验', ok:false, detail:'校验中：数据源读写权限...'}
  ]};
  UI.switchTab('ideTab', 4, 1, 1);
  var tabs = p.tables, params = p.params;
  var d0 = tabs.length? '解析到上游表 '+tabs.length+' 张：'+tabs.slice(0,3).join('、')+(tabs.length>3?' 等':'')+' → 已生成血缘注册建议（可在「血缘分析」查看）' : '未检测到表引用（常量查询），无需注册血缘';
  var d1 = params.length? '检测到 '+params.length+' 个参数引用：${'+params.join('}、${')+'} → 均已在全局参数/内置时间参数中注册 ✓' : '未引用参数（无 ${} 占位符），跳过参数注入检查 ✓';
  var d2 = '当前用户 '+DB.user.name+' 对 '+DB.datasources[5].name+' 具备查询/导出权限 ✓，产出表写入权限已校验 ✓';
  setTimeout(function(){ if(A._ideVerify){ A._ideVerify.checks[0].ok=true; A._ideVerify.checks[0].detail=d0; A._ideTab(4); } }, 500);
  setTimeout(function(){ if(A._ideVerify){ A._ideVerify.checks[1].ok=true; A._ideVerify.checks[1].detail=d1; A._ideTab(4); } }, 1000);
  setTimeout(function(){
    if(!A._ideVerify) return;
    A._ideVerify.checks[2].ok=true; A._ideVerify.checks[2].detail=d2; A._ideVerify.done=true; A._ideTab(4);
    if(p.ok) UI.toast('验证通过：血缘 / 参数 / 权限 三项校验完成', 'success');
    else UI.toast('验证完成，但语法存在 '+p.problems.length+' 个问题，建议先「语法解析」', 'warn');
  }, 1500);
};

/* ---- ✦ AI 优化（AI助手场景动作 A.ideAiFmt：追加优化注释块 + toast） ---- */
A.ideAiFmt = function(){
  var ed = document.getElementById('ideEditor'); if(!ed) return;
  var sql = ed.value;
  if(!sql.trim()){ UI.toast('当前SQL为空，无法优化', 'warn'); return; }
  if(sql.indexOf('✦ AI 优化建议')<0){
    ed.value = sql + '\n\n/* ✦ AI 优化建议（'+now+' 23:50 生成，应用后可删除本注释块）\n'
      + '   1. WHERE dt=\'${biz_date}\' 命中分区裁剪，预计扫描量 -86%\n'
      + '   2. ORDER BY pay_amount_sum DESC 建议追加 LIMIT，避免全量排序落盘\n'
      + '   3. 字段请显式列出（禁用 SELECT *），并补充字段注释口径\n'
      + '   4. 发布时勾选「参数替换」，${biz_date} 由调度按 T-1 注入\n*/';
  }
  DB.ideTabs[DB.ideActive].sql = ed.value;
  UI.toast('AI 优化完成：已在代码尾部追加 4 条优化建议注释', 'success');
};

/* ---- 发布（modal 确认表单 → 产出模型/描述 → 写入 DB.etlTasks 真闭环） ---- */
A.idePublish = function(){
  var ed = document.getElementById('ideEditor'); if(!ed) return;
  var sql = ed.value; DB.ideTabs[DB.ideActive].sql = sql;
  if(!sql.trim()){ UI.toast('当前查询为空，无法发布', 'warn'); return; }
  var tab = DB.ideTabs[DB.ideActive];
  var models = DB.models.filter(function(m){return m.status==='published';});
  UI.modal({title:'发布为 ETL 任务', w:'w-md',
    footer:'<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="A.idePublishGo()">确认发布</button>',
    body: UI.desc([['来源', 'SQL IDE · '+UI.esc(tab.name)],['SQL 规模', sql.length+' 字符 / '+sql.split('\n').length+' 行'],
      ['引用参数', (A._parseSql(sql).params.map(function(p){return '${'+p+'}';}).join('、'))||'无']])
    + '<div class="form-grid" style="margin-top:10px">'
    + UI.fInput('任务名称', 'pb_name', {value:tab.name+'-发布', req:true, full:true})
    + UI.fSelect('产出模型', 'pb_model', models.map(function(m){return {v:m.id, t:m.code+'（'+m.layer+' · '+m.name+'）'};}), {value:(models[0]||{}).id, full:true, help:'发布后按产出模型注册血缘，并生成 DAG 挂载建议'})
    + UI.fTextarea('任务描述', 'pb_desc', {rows:3, full:true, ph:'如：支付主题日汇总加工，T-1 调度，产出 dws_pay_summary_daily'})
    + '</div>'
    + '<div class="lock-tip">发布动作：新建「SQL任务」类型的 ETL 任务并发布 → 注册产出血缘 → 生成 DAG 挂载建议（可在「批处理任务」与「工作流调度」中查看）。</div>'});
};
A.idePublishGo = function(){
  var name = UI.val('pb_name');
  if(!name){ UI.toast('请填写任务名称', 'warn'); return false; }
  var ed = document.getElementById('ideEditor');
  var sql = ed? ed.value : DB.ideTabs[DB.ideActive].sql;
  var model = DB.models.find(function(m){return m.id===UI.val('pb_model');});
  DB.etlTasks.push({
    id:'ETL'+String(DB.etlTasks.length+1).padStart(3,'0'),
    name:name,
    code:'etl_'+(model? model.code : name).toLowerCase().replace(/[^a-z0-9_]+/g,'_'),
    type:'SQL任务', status:'published', owner:DB.user.name,
    sql:sql, cron:'0 0 4 * * ?', lastRun:'-', updatedAt:now+' 23:55',
    desc:UI.val('pb_desc') || ('SQL IDE 发布：产出 '+(model? model.code : '待注册模型'))
  });
  UI.closeModal();
  UI.toast('已发布为 ETL 任务并挂载 DAG 建议', 'success');
  AI.show('发布完成 ✦\n· 已创建 SQL 类型 ETL 任务「'+name+'」并置为已发布\n· 产出模型：'+(model? model.code+'（'+model.layer+'）':'待注册')+'，血缘注册建议已生成\n· DAG 建议：挂载至「订单主题日增」工作流，依赖 dwd_order_pay_detail 分区就绪后每日 04:00 执行\n· 可前往「批处理任务」查看新任务，或在工作流画布中确认挂载位置。');
};
A.ideComplete = function(ed){
  /* 简易补全提示 */
  var v = ed.value;
  if(/\b(dws_pay_summary_daily)\s*\.?\s*$/i.test(v) && !ed._hinted){
    ed._hinted = true;
    UI.toast('补全提示：stat_date / channel / pay_user_cnt / pay_order_cnt / pay_amount_sum', 'info');
    setTimeout(function(){ ed._hinted = false; }, 3000);
  }
};
A._ideTab = function(i){
  var b = document.getElementById('ideTabBody'); if(!b) return;
  if(i===0){
    var res = A._ideResult;
    b.innerHTML = UI.card('查询结果'+(res?'（'+res.rows+' 行 · '+res.dur+'）':''),
      (res? UI.tbl({id:'t_ideRes', rowKey:'k', pageSize:10, searchKeys:['k','c'],
        data:function(){ return [{k:'ALIPAY', c:3210, o:4102, s:528210.55},{k:'WECHAT', c:2890, o:3640, s:451870.20}]; },
        cols:[{t:'channel',k:'k',render:function(r){return '<span class="mono">'+r.k+'</span>';}},{t:'pay_user_cnt',k:'c',render:function(r){return '<span class="mono">'+r.c+'</span>';}},{t:'pay_order_cnt',k:'o',render:function(r){return '<span class="mono">'+r.o+'</span>';}},{t:'pay_amount_sum',k:'s',render:function(r){return '<span class="mono">'+r.s.toFixed(2)+'</span>';}}],
        ops:null, toolbarActs:function(){ return '<button class="btn btn-sm" onclick="UI.download(\'query_result.csv\',\'channel,pay_user_cnt,pay_order_cnt,pay_amount_sum\\nALIPAY,3210,4102,528210.55\\nWECHAT,2890,3640,451870.20\',\'text/csv\')">⇩ CSV</button><button class="btn btn-sm" onclick="UI.download(\'query_result.json\',\'[{&quot;channel&quot;:&quot;ALIPAY&quot;},{&quot;channel&quot;:&quot;WECHAT&quot;}]\',\'application/json\')">⇩ JSON</button><button class="btn btn-sm" onclick="UI.download(\'query_result.sql\',\'INSERT INTO dws_pay_summary_daily VALUES (...);\')">⇩ INSERT</button><button class="btn btn-sm" onclick="UI.download(\'query_result.xlsx\',\'channel\\tpay_user_cnt\\tpay_order_cnt\\tpay_amount_sum\\nALIPAY\\t3210\\t4102\\t528210.55\',\'application/vnd.ms-excel\')">⇩ Excel</button>'; }})
        : '<div class="empty"><span class="e-ico">▶</span><p>编写SQL后点击「运行测试」查看结果</p></div>'));
  }
  if(i===1){
    b.innerHTML = UI.card('执行历史', UI.tbl({
      id:'t_ideHis', rowKey:'id', pageSize:8, searchKeys:['sql'],
      data:function(){ return DB.ideHistory; },
      cols:[
        {t:'SQL', k:'sql', render:function(r){ return '<span class="mono" style="font-size:11.5px">'+UI.esc(r.sql.length>56? r.sql.slice(0,56)+'…' : r.sql)+'</span>'; }},
        {t:'数据源', render:function(r){ var d = DB.datasources.find(function(x){return x.id===r.ds;}); return d? d.name : '-'; }},
        {t:'行数', render:function(r){ return '<span class="mono">'+r.rows+'</span>'; }},
        {t:'耗时', k:'dur'},
        {t:'时间', k:'time'},
        {t:'收藏', render:function(r){ return '<a onclick="A.ideStar(\''+r.id+'\')">'+(r.star?'★':'☆')+'</a>'; }}
      ],
      ops:function(r){ return '<a onclick="A.ideReuse(\''+r.id+'\')">重新执行</a><a onclick="A.ideCopy(\''+r.id+'\')">复制</a>'; }
    }));
  }
  if(i===2){
    var stars = DB.ideHistory.filter(function(h){return h.star;});
    b.innerHTML = UI.card('收藏的SQL', stars.length? UI.tbl({id:'t_ideStar', rowKey:'id', pageSize:8, searchKeys:['sql'],
      data:function(){ return stars; },
      cols:[{t:'SQL',k:'sql',render:function(r){return '<span class="mono" style="font-size:11.5px">'+UI.esc(r.sql.length>70? r.sql.slice(0,70)+'…':r.sql)+'</span>';}},{t:'时间',k:'time'}],
      ops:function(r){ return '<a onclick="A.ideReuse(\''+r.id+'\')">使用</a><a onclick="A.ideStar(\''+r.id+'\')">取消收藏</a>'; }}) : '<div class="empty"><span class="e-ico">★</span><p>在执行历史中点击 ☆ 收藏常用SQL</p></div>');
  }
  if(i===3){
    var p = A._ideParse;
    if(!p){
      b.innerHTML = UI.card('语法解析', '<div class="empty"><span class="e-ico">✓</span><p>点击工具栏「✓ 语法解析」解析当前SQL：关键字配对 / 括号计数 / 分号结尾 / 表·字段·参数抽取</p></div>');
    } else {
      var treeHtml = p.stmts.map(function(s, si){
        return '<div style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:8px;background:#f8fafc;font-size:12px">'
          +'<b>语句 '+(si+1)+'：'+s.type+'</b><span style="color:var(--text-3)">（第 '+s.start+'~'+s.end+' 行）</span>'
          +'<div style="margin-top:5px;color:var(--text-2)">子句链：'+(s.clauses.length? s.clauses.join(' → ') : '—')+'</div>'
          +'<div style="margin-top:3px;color:var(--text-2)">表引用：'+(s.tables.length? s.tables.map(function(t){return '<span class="mono">'+UI.esc(t)+'</span>';}).join('、') : '—')+'</div>'
          +'<div style="margin-top:3px;color:var(--text-2)">字段引用（'+s.fields.length+'）：'+(s.fields.length? '<span class="mono" style="font-size:11.5px">'+UI.esc(s.fields.slice(0,6).join(' , '))+(s.fields.length>6?' …':'')+'</span>' : '—')+'</div>'
          +(s.params.length? '<div style="margin-top:3px;color:var(--text-2)">参数：'+s.params.map(function(x){return '<span class="tag tag-cyan" style="margin-right:4px">${'+x+'}</span>';}).join('')+'</div>' : '')
          +'</div>';
      }).join('');
      var probHtml = p.ok
        ? '<div class="checker-line ok"><span>✓</span><b>解析通过</b><span style="margin-left:auto">未发现语法问题</span></div>'
        : p.problems.map(function(x){ return '<div class="checker-line err"><span>✗</span><b>第 '+x.line+' 行</b><span>'+UI.esc(x.msg)+'</span></div>'; }).join('');
      b.innerHTML = UI.card('语法解析'+(p.ok?'（通过）':'（'+p.problems.length+' 个问题）'),
        UI.kv([['语句数', p.stmts.length+' 条'], ['表引用', p.tables.length? p.tables.length+' 张（'+UI.esc(p.tables.join('、'))+'）':'—'],
               ['字段引用', p.fields+' 个（SELECT 列）'], ['参数列表', p.params.length? p.params.map(function(x){return '${'+x+'}';}).join('、'):'—']])
        + '<div style="margin-top:12px;font-size:12.5px;font-weight:600;margin-bottom:8px">语法树概要</div>' + treeHtml
        + '<div style="margin-top:12px;font-size:12.5px;font-weight:600;margin-bottom:8px">问题列表</div>' + probHtml);
    }
  }
  if(i===4){
    var v = A._ideVerify;
    if(!v){
      b.innerHTML = UI.card('验证', '<div class="empty"><span class="e-ico">⊘</span><p>点击工具栏「⊘ 验证」执行：表血缘解析 / 参数引用检测 / 权限校验 三项检查</p></div>');
    } else {
      b.innerHTML = UI.card('验证（'+v.time+'）',
        v.checks.map(function(c){
          return '<div class="checker-line '+((v.done||c.ok)?'ok':'run')+'"><span>'+(c.ok?'✓':'⏳')+'</span><b>'+c.name+'</b>'
            +'<span style="color:var(--text-3);flex:1;text-align:right">'+UI.esc(c.detail)+'</span></div>';
        }).join('')
        + (v.done? '<div class="banner banner-success" style="margin-top:10px;margin-bottom:0"><span class="b-ico">✓</span><span>验证完成：血缘 / 参数 / 权限 三项通过，可发布为 ETL 任务。</span></div>' : ''));
    }
  }
  if(i===5){
    b.innerHTML = DB.sqlFuncs.map(function(g){
      return UI.card(g.cat, g.items.map(function(f){ return '<div class="kv-row"><span class="v mono" style="font-size:12px">'+f+'</span></div>'; }).join(''));
    }).join('') + '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>函数参考仅覆盖 P0 优先支撑数据库类型（万里/高斯/达梦/MySQL/Oracle/Doris/Hive）的通用函数；数据库专有函数排后迭代。</span></div>';
  }
};
A.ideStar = function(id){ var h = DB.ideHistory.find(function(x){return x.id===id;}); h.star = !h.star; UI.toast(h.star?'已收藏':'已取消收藏', 'success'); A._ideTab(1); };
A.ideReuse = function(id){ var h = DB.ideHistory.find(function(x){return x.id===id;}); DB.ideTabs[DB.ideActive].sql = h.sql; document.getElementById('ideEditor').value = h.sql; UI.toast('SQL已填入编辑器，可直接执行', 'success'); };
A.ideCopy = function(id){ UI.toast('SQL已复制到剪贴板', 'success'); };
})();
