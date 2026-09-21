/* ============================================================
   M14 脚本任务（脚本库/环境与依赖/远程执行SSH）
   闭环：脚本编写 → 选择执行方式(本地/SSH) → 执行日志 → 失败告警/重跑
   ============================================================ */
(function(){
/* ---- 脚本库 ---- */
App.reg('#/script/list', '脚本库', function(){
  var html = UI.pageHead('脚本任务',
    '在线脚本开发与托管：Python / Shell（Java 编译执行排后），支持本地执行与远程 SSH 执行，参数引用 ${global_param}',
    '<button class="btn btn-primary" onclick="A.scCreate()">+ 新建脚本</button>'
    +'<button class="btn" onclick="App.go(\'#/script/env\')">环境与依赖</button>');
  html += UI.card('脚本列表', UI.tbl({
    id:'t_sc', rowKey:'id', pageSize:8, searchKeys:['id','name','lang'], searchPh:'搜索脚本',
    filters:[
      {k:'lang', label:'语言', options:[{v:'Python',t:'Python'},{v:'Shell',t:'Shell'},{v:'Java',t:'Java'}]},
      {k:'status', label:'状态', options:[{v:'published',t:'已发布'},{v:'draft',t:'草稿'},{v:'disabled',t:'已停用'}]}
    ],
    data:function(){ return DB.scripts; },
    cols:[
      {t:'脚本', k:'name', sortable:true, render:function(r){
        return '<div><a onclick="A.scView(\''+r.id+'\')"><b>'+r.name+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+r.lang+'</div></div>';}},
      {t:'语言', k:'lang', render:function(r){return tag(r.lang, r.lang==='Python'?'blue':r.lang==='Shell'?'green':'orange');}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}},
      {t:'负责人', k:'owner'},{t:'更新日期', k:'updated'}
    ],
    ops:function(r){
      return '<a onclick="A.scView(\''+r.id+'\')">查看</a>'
        +'<a onclick="A.scRun(\''+r.id+'\')">执行</a>'
        +'<a onclick="A.scEdit(\''+r.id+'\')">编辑</a>'
        +'<a onclick="A.scLinkSched(\''+r.id+'\')">关联调度</a>'
        +(r.status==='draft'? '<a onclick="A.scPublish(\''+r.id+'\')">发布</a>':'')
        +'<a onclick="UI.toggleStatus(DB.scripts.find(function(x){return x.id===\''+r.id+'\'}))">'+(r.status==='disabled'?'启用':'停用')+'</a>'
        +'<a class="danger" onclick="UI.delRow(DB.scripts, \'id\', \''+r.id+'\', \''+r.name+'\')">删除</a>';
    }}));
  html += UI.card('执行日志', UI.tbl({
    id:'t_sclog', rowKey:'id', pageSize:5, searchKeys:['id','script','mode'], searchPh:'搜索日志',
    filters:[{k:'status', label:'结果', options:[{v:'success',t:'成功'},{v:'failed',t:'失败'}]}],
    data:function(){ return DB.execLogs; },
    cols:[
      {t:'日志', k:'id', render:function(r){return '<a onclick="A.scLog(\''+r.id+'\')"><b>'+r.id+'</b></a><div style="font-size:11px;color:var(--text-3)">'+UI.esc(r.script)+'</div>';}},
      {t:'方式', k:'mode'},
      {t:'开始', k:'start'},{t:'耗时', k:'dur'},
      {t:'结果', render:function(r){return st(r.status);}}
    ],
    ops:function(r){ return '<a onclick="A.scLog(\''+r.id+'\')">日志</a>'+(r.status==='failed'?'<a onclick="A.scRerun(\''+r.id+'\')">重跑</a>':''); }}));
  return html;
});
A.scFormFields = function(d){
  var sid = d.id || '';
  return '<div class="form-grid">'
    + UI.fInput('脚本名称', 'sc_name', {value:d.name, req:true})
    + UI.fSelect('语言', 'sc_lang', [{v:'Python',t:'Python（本地/远程SSH）'},{v:'Shell',t:'Shell（本地/远程SSH）'},{v:'Java',t:'Java（查看为主，编译执行排后）'}], {value:d.lang||'Python'})
    + UI.fSelect('Python 环境（Python脚本）', 'sc_venv', DB.pyEnvs.map(function(v){return {v:v.name,t:v.name+'（Py'+v.python+' · '+v.pkgs.length+'包）'};}).concat([{v:'-',t:'不适用'}]), {value:d.venv||'py3-data'})
    + '</div>'
    /* 编辑器工具条：运行测试 / 语法检查 / 保存版本 / 提交调度 */
    + '<div class="form-item full"><div class="f-label">脚本内容<span class="req">*</span></div>'
    + '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:2px 0 8px">'
    + '<button class="btn btn-sm" onclick="A.scTestRun()">▶ 运行测试</button>'
    + '<button class="btn btn-sm" onclick="A.scLint()">✓ 语法检查</button>'
    + '<button class="btn btn-sm" onclick="A.scSaveVersion(\''+sid+'\')">💾 保存版本</button>'
    + '<button class="btn btn-sm" onclick="A.scSubmitSched(\''+sid+'\')">提交调度</button>'
    + '<span style="font-size:11px;color:var(--text-3);margin-left:auto">'+(d.lang||'Python')+' 关键语法提示 · 参数注入 ${env} / ${dw_user} / ${biz_date}</span>'
    + '</div>'
    + A.scEditor('sc_code', d.code||'')
    + '<div id="sc_test_out" style="margin-top:10px"></div>'
    + '</div>'
    + '<div class="lock-tip">参数引用：${env} / ${dw_user} 等全局参数与 ${biz_date} 内置时间参数在执行时注入；Java 脚本当前仅支持在线查看。</div>';
};
/* ---- 行号编辑器（textarea + 行号列，随输入/滚动同步） ---- */
A.scEditor = function(id, code){
  return '<div style="display:flex;border:1px solid #cbd5e1;border-radius:8px;overflow:hidden">'
    + '<pre id="'+id+'_gut" class="mono" style="margin:0;flex-shrink:0;min-width:38px;padding:10px 6px 10px 10px;text-align:right;background:#0a1120;color:#44546e;font-family:Consolas,monospace;font-size:12px;line-height:1.8;border-right:1px solid #1c2a44;user-select:none;overflow:hidden">'+A._gutNums(code)+'</pre>'
    + '<textarea id="'+id+'" wrap="off" spellcheck="false" style="flex:1;min-width:0;border:none;outline:none;resize:vertical;background:#0d1424;color:#9fb2d0;font-family:Consolas,monospace;font-size:12px;line-height:1.8;padding:10px 12px;min-height:240px;white-space:pre;overflow:auto" oninput="A.scGutter(\''+id+'\')" onscroll="A.scGutter(\''+id+'\')">'+UI.esc(code)+'</textarea></div>';
};
A._gutNums = function(code){
  var n = (code||'').split('\n').length, out = [], i;
  for(i=1;i<=n;i++) out.push(i);
  return out.join('\n');
};
A.scGutter = function(id){
  var t = document.getElementById(id), g = document.getElementById(id+'_gut');
  if(!t || !g) return;
  g.innerHTML = A._gutNums(t.value);
  g.scrollTop = t.scrollTop;
};
/* ---- 工具条：▶ 运行测试（沙箱试跑，不产生正式日志） ---- */
A.scTestRun = function(){
  var code = UI.val('sc_code'), lang = UI.val('sc_lang') || 'Python';
  var out = document.getElementById('sc_test_out'); if(!out) return;
  if(!code.trim()){ UI.toast('请先填写脚本内容', 'warn'); return; }
  if(lang==='Java'){ UI.toast('Java 编译执行排后（P0 范围外），仅支持查看', 'warn'); return; }
  out.innerHTML = '<div class="checker-line run"><span>⏳</span><b>运行测试中...</b><span style="margin-left:auto">'+lang+' · 本地容器沙箱（只读权限）</span></div>';
  setTimeout(function(){
    if(!document.getElementById('sc_test_out')) return;
    var log = '[TEST 23:40:01] [INFO] 参数注入完成：env=prod / dw_user=datara_etl / biz_date=2026-09-11\n'
      + '[TEST 23:40:02] [INFO] 开始执行 '+lang+' 脚本（沙箱）...\n'
      + '[TEST 23:40:0'+(4+Math.floor(Math.random()*4))+'] [OK] 退出码 0，测试通过（结果不写入执行日志）';
    out.innerHTML = '<div class="checker-line ok"><span>✓</span><b>运行测试通过</b><span style="margin-left:auto">耗时 '+(2+Math.floor(Math.random()*4))+'s</span></div>'
      + '<pre class="mono" style="background:#0d1424;color:#9fb2d0;border-radius:8px;padding:10px 12px;font-size:11.5px;line-height:1.7;max-height:180px;overflow:auto;margin:0">'+UI.esc(log)+'</pre>';
    UI.toast('测试通过：退出码 0', 'success');
  }, 900);
};
/* ---- 工具条：✓ 语法检查（Python/Shell 关键提示） ---- */
A.scLint = function(){
  var code = UI.val('sc_code'), lang = UI.val('sc_lang') || 'Python';
  var out = document.getElementById('sc_test_out'); if(!out) return;
  if(!code.trim()){ UI.toast('请先填写脚本内容', 'warn'); return; }
  if(lang==='Java'){ UI.toast('Java 语法检查排后（P0 范围外），当前仅支持查看', 'warn'); return; }
  var issues = [], lines = code.split('\n'), i, depth = 0, openLine = 0;
  for(i=0;i<lines.length;i++){
    var ln = lines[i].replace(/#.*$/, '');
    var bo = (ln.match(/\(/g)||[]).length, bc = (ln.match(/\)/g)||[]).length;
    if(depth===0 && bo>bc) openLine = i+1;
    depth += bo - bc;
    if(depth < 0){ issues.push({line:i+1, msg:'圆括号不匹配：多余的 ")"'}); depth = 0; }
    var s = ln.trim();
    if(!s) continue;
    if(lang==='Python'){
      if(/\b(if|elif|else|for|while|def|class|try|except|finally|with)\b/.test(s) && s.indexOf(':')<0)
        issues.push({line:i+1, msg:'Python 语句块缺少冒号 ":"'});
      if(/\t/.test(lines[i].match(/^\s*/)[0]) && lines[i].match(/^\t/))
        issues.push({line:i+1, msg:'建议统一使用 4 空格缩进（检测到 Tab）'});
    } else if(lang==='Shell'){
      if(/^if\s/.test(s) && !/;\s*then$/.test(s) && !/\bthen\b/.test(s))
        issues.push({line:i+1, msg:'if 语句缺少 then（建议写成 if ...; then）'});
    }
  }
  if(depth > 0) issues.push({line:openLine, msg:'第 '+openLine+' 行的 "(" 未闭合'});
  if(lang==='Python'){
    if((code.match(/\bdef\b/g)||[]).length && code.indexOf('return')<0 && code.indexOf('print')<0)
      issues.push({line:0, msg:'函数缺少输出/返回，建议补充 return 或日志打印'});
  } else if(lang==='Shell'){
    var ifs = (code.match(/\bif\b/g)||[]).length, fis = (code.match(/\bfi\b/g)||[]).length;
    var dos = (code.match(/\bdo\b/g)||[]).length, dones = (code.match(/\bdone\b/g)||[]).length;
    if(ifs !== fis) issues.push({line:0, msg:'if/fi 不配对：if '+ifs+' 个，fi '+fis+' 个'});
    if(dos !== dones) issues.push({line:0, msg:'do/done 不配对：do '+dos+' 个，done '+dones+' 个'});
  }
  if(!issues.length){
    out.innerHTML = '<div class="checker-line ok"><span>✓</span><b>语法检查通过</b><span style="margin-left:auto">'+lang+' · '+lines.length+' 行</span></div>'
      + '<div class="banner banner-info" style="margin-bottom:0"><span class="b-ico">ℹ</span><span>'+(lang==='Python'?'检查项：括号配对 / 冒号 / 缩进；提示：${biz_date} 等参数在执行时注入，无需转义。':'检查项：括号配对 / if-fi / do-done 配对；提示：引用变量请使用 "$var" 防空格拆词。')+'</span></div>';
    UI.toast('语法检查通过', 'success');
  } else {
    out.innerHTML = '<div class="checker-line err"><span>✗</span><b>发现 '+issues.length+' 个疑似问题</b></div>'
      + issues.map(function(x){ return '<div class="checker-line err"><span>·</span><b>'+(x.line? '第 '+x.line+' 行':'全局')+'</b><span>'+UI.esc(x.msg)+'</span></div>'; }).join('');
    UI.toast('语法检查发现 '+issues.length+' 个疑似问题', 'warn');
  }
};
/* ---- 工具条：💾 保存版本（DB.scriptVersions 懒初始化，最多保留 10 个版本） ---- */
A.scSaveVersion = function(sid){
  var code = UI.val('sc_code');
  if(!code.trim()){ UI.toast('脚本内容为空，无法保存版本', 'warn'); return; }
  if(!sid){ UI.toast('请先点击「确定」保存脚本草稿，再保存版本', 'warn'); return; }
  var d = DB.scripts.find(function(x){return x.id===sid;});
  if(!d) return;
  d.code = code; d.updated = now;
  DB.scriptVersions = DB.scriptVersions || {};
  var arr = DB.scriptVersions[sid] = DB.scriptVersions[sid] || [];
  var v = (arr.length? arr[0].v : 0) + 1;
  arr.unshift({v:v, time:now+' 23:45', by:DB.user.name, note:'编辑器保存'});
  if(arr.length > 10) arr.pop();
  UI.toast('已保存版本 v'+v+'（共 '+arr.length+' 个版本，可在版本历史回滚）', 'success');
};
/* ---- 工具条：提交调度（保存后打开关联调度，脚本↔DAG 闭环） ---- */
A.scSubmitSched = function(sid){
  if(!sid){ UI.toast('请先保存脚本草稿后再提交调度', 'warn'); return; }
  var d = DB.scripts.find(function(x){return x.id===sid;});
  if(!d) return;
  if(d.lang==='Java'){ UI.toast('Java 脚本暂不支持调度（编译执行排后）', 'warn'); return; }
  var code = UI.val('sc_code');
  if(code) { d.code = code; d.updated = now; }
  UI.closeDrawer();
  UI.toast('脚本已保存，正在打开关联调度...', 'info');
  A.scLinkSched(sid);
};
/* ---- 关联调度：查看/挂载 DAG 工作流引用（脚本↔调度闭环） ---- */
A.scRefs = function(sid){
  DB.scriptRefs = DB.scriptRefs || {
    SC001:[{wf:'WF004', node:'凭证清洗（脚本节点）', note:'前置：同步ERP凭证成功后触发；以退出码 0 判定成功，失败重试 1 次'}]
  };
  return DB.scriptRefs[sid] || (DB.scriptRefs[sid] = []);
};
A.scLinkSched = function(sid){
  var d = DB.scripts.find(function(x){return x.id===sid;});
  if(!d) return;
  var refs = A.scRefs(sid);
  var body = refs.length
    ? '<div style="font-size:12px;color:var(--text-2);margin-bottom:8px">该脚本已被以下 <b>'+refs.length+'</b> 个 DAG 工作流引用：</div>'
      + refs.map(function(r){
          var wf = DB.workflows.find(function(w){return w.id===r.wf;});
          return '<div class="checker-line ok"><span>🔗</span><div style="flex:1"><b>'+UI.esc(wf? wf.name+'（'+wf.id+'）' : r.wf)+'</b>'
            +'<div style="font-size:11px;color:var(--text-3);margin-top:2px">'+UI.esc(r.node)+(wf? ' · cron '+wf.cron+' · '+(wf.status==='online'?'调度中':'草稿') : '')+'</div>'
            +'<div style="font-size:11px;color:var(--text-3)">'+UI.esc(r.note)+'</div></div></div>';
        }).join('')
    : '<div class="empty" style="padding:18px"><span class="e-ico">🔗</span><p>未挂载：该脚本尚未被任何 DAG 工作流引用，可挂载后参与周期调度</p></div>';
  body += '<div style="border-top:1px dashed var(--border);margin-top:12px;padding-top:12px">'
    + UI.fSelect('挂载到工作流', 'scs_wf', DB.workflows.map(function(w){return {v:w.id, t:w.name+'（'+w.id+' · '+w.nodes+'节点 · '+w.status+'）'};}), {})
    + '<div class="f-help">挂载后作为「脚本节点」追加至所选工作流：依赖上游节点成功 → 注入参数执行 → 退出码 0 判定成功，失败按重试策略重试并告警。</div></div>';
  UI.modal({title:'关联调度 - '+d.name+'（'+d.id+'）', w:'w-md',
    footer:'<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="A.scLinkGo(\''+sid+'\')">确认挂载</button>',
    body:body});
};
A.scLinkGo = function(sid){
  var wfid = UI.val('scs_wf');
  var wf = DB.workflows.find(function(w){return w.id===wfid;});
  if(!wf){ UI.toast('请选择工作流', 'warn'); return false; }
  var d = DB.scripts.find(function(x){return x.id===sid;});
  if(!d) return false;
  var refs = A.scRefs(sid);
  if(refs.some(function(r){return r.wf===wfid;})){ UI.toast('该脚本已挂载到「'+wf.name+'」，请更换工作流', 'warn'); return false; }
  refs.push({wf:wfid, node:'脚本节点：'+d.name, note:'依赖上游节点产出就绪后执行；退出码 0 判定成功，失败重试 1 次并告警'});
  UI.closeModal();
  UI.toast('已挂载到「'+wf.name+'」', 'success');
  UI.toast('依赖说明：上游节点成功 → 执行 '+d.id+' '+d.name+'（退出码 0）→ 释放下游节点', 'info');
};
A.scCreate = function(){ UI.drawer({title:'新建脚本', w:'w-xl', body:A.scFormFields({}), onOk:function(){
  var name = UI.val('sc_name');
  if(!name||!UI.val('sc_code')){ UI.toast('请填写脚本名称与内容', 'warn'); return false; }
  DB.scripts.push({id:'SC00'+(DB.scripts.length+1), name:name, lang:UI.val('sc_lang'), status:'draft', owner:DB.user.name, updated:now, code:UI.val('sc_code'), venv:UI.val('sc_venv')});
  UI.toast('脚本已保存（草稿），可发布后执行', 'success');}}); };
A.scEdit = function(id){ var d = DB.scripts.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑脚本 - '+d.name, w:'w-xl', body:A.scFormFields(d), onOk:function(){
    Object.assign(d, {name:UI.val('sc_name'), lang:UI.val('sc_lang'), code:UI.val('sc_code'), updated:now, venv:UI.val('sc_venv')});
    UI.toast('脚本已保存', 'success');}}); };
A.scView = function(id){
  var d = DB.scripts.find(function(x){return x.id===id;});
  var his = DB.execLogs.filter(function(l){return l.script.indexOf(id+' ')===0;});
  var hisHtml = his.length
    ? '<table style="width:100%;border-collapse:collapse;font-size:12px">'
      +'<thead><tr>'+['时间','方式','结果','耗时','日志摘要'].map(function(h){ return '<th style="text-align:left;padding:6px 8px;background:#f7f9fc;border-bottom:1px solid var(--border)">'+h+'</th>'; }).join('')+'</tr></thead><tbody>'
      + his.slice(0,5).map(function(l){
          var sum = (l.content.split('\n').filter(function(x){return x.indexOf('[ERROR]')>=0||x.indexOf('[OK]')>=0;})[0] || l.content.split('\n')[0] || '').slice(0,48);
          return '<tr>'
            +'<td style="padding:6px 8px;border-bottom:1px solid var(--border)">'+l.start+'</td>'
            +'<td style="padding:6px 8px;border-bottom:1px solid var(--border);color:var(--text-3)">'+l.mode+'</td>'
            +'<td style="padding:6px 8px;border-bottom:1px solid var(--border)">'+st(l.status)+'</td>'
            +'<td style="padding:6px 8px;border-bottom:1px solid var(--border)">'+l.dur+'</td>'
            +'<td style="padding:6px 8px;border-bottom:1px solid var(--border)"><span class="mono" style="font-size:11px">'+UI.esc(sum)+'…</span> <a onclick="A.scLog(\''+l.id+'\')">详情</a></td></tr>';
        }).join('')+'</tbody></table>'
    : '<div style="font-size:12px;color:var(--text-3);padding:6px 0">暂无执行记录，点击右上角「执行」运行一次</div>';
  UI.modal({title:'脚本查看 - '+d.name+'（'+d.lang+'）', w:'w-xl', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="UI.closeModal();A.scRun(\''+d.id+'\')">执行</button>', body:
    '<pre class="mono" style="background:#0d1424;color:#9fb2d0;border-radius:8px;padding:14px;font-size:11.5px;line-height:1.8;max-height:300px;overflow:auto;margin:0">'+UI.esc(d.code)+'</pre>'
    + '<div style="margin-top:14px"><div style="font-size:12.5px;font-weight:600;margin-bottom:8px">执行历史（最近 '+Math.min(his.length,5)+' 条 / 共 '+his.length+' 条）</div>'+hisHtml+'</div>'});
};
A.scPublish = function(id){
  var d = DB.scripts.find(function(x){return x.id===id;});
  UI.confirm({title:'发布脚本', msg:'发布「'+d.name+'」？', detail:'发布后可在执行/被工作流脚本节点引用。', onOk:function(){ d.status='published'; UI.toast('脚本已发布', 'success'); App.resolve(); }});
};
A.scRun = function(id){
  var d = DB.scripts.find(function(x){return x.id===id;});
  if(d.lang==='Java'){ UI.toast('Java 编译执行排后（P0 范围外），仅支持查看', 'warn'); return; }
  UI.drawer({title:'执行脚本 - '+d.name, w:'w-md', body:
    UI.fSelect('执行方式', 'sr_mode', [{v:'本地执行',t:'本地执行（平台容器）'},{v:'远程执行(SSH)',t:'远程执行（SSH 节点）'}], {})
    + UI.fSelect('远程节点', 'sr_node', DB.remoteNodes.map(function(n){return {v:n.name,t:n.name+'（'+n.ip+' · '+(n.status==='online'?'在线':'离线')+'）'};}), {})
    + UI.fInput('参数覆盖（可选）', 'sr_args', {ph:'如：biz_date=2026-09-11'}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.scRunGo(\''+id+'\')">▶ 立即执行</button>'});
};
A.scRunGo = function(id){
  var d = DB.scripts.find(function(x){return x.id===id;});
  var mode = UI.val('sr_mode');
  var node = DB.remoteNodes.find(function(n){return n.name===UI.val('sr_node');});
  if(mode==='远程执行(SSH)' && node && node.status!=='online'){
    UI.confirm({title:'节点不可达', danger:true, msg:'远程节点「'+node.name+'」离线（最近心跳 '+node.lastPing+'）', detail:'请选择其他节点或检查网络/VPN。'}); return;
  }
  UI.closeDrawer();
  UI.toast('正在'+mode+'「'+d.name+'」（'+(mode==='远程执行(SSH)'?UI.val('sr_node'):'本地')+'）...', 'info');
  setTimeout(function(){
    var ok = d.lastExecFail!==true;
    var log = {id:'LOG'+now.replace(/-/g,'')+'-00'+(DB.execLogs.length+1), script:d.id+' '+d.name, mode:mode+(mode==='远程执行(SSH)'?': '+node.ip:''), status:ok?'success':'failed', start:now+' 23:20', dur:ok?'4s':'12s',
      content: ok? '[23:20:01] [INFO] 参数注入完成（env/dw_user/biz_date）\n[23:20:02] [INFO] 开始执行 '+d.lang+' 脚本...\n[23:20:0'+(3+Math.floor(Math.random()*5))+'] [OK] 执行完成，退出码 0'
        : '[23:20:01] [INFO] 开始执行...\n[23:20:10] [ERROR] FileNotFoundError: 上游分区不存在\n[23:20:12] [WARN] 退出码 1，已触发告警（邮件+短信）'};
    DB.execLogs.unshift(log);
    d.lastExecFail = !ok;
    UI.modal({title:'执行结果', w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal();App.resolve()">关闭</button>', body:
      '<div class="checker-line '+(ok?'ok':'err')+'"><span>'+(ok?'✓':'✗')+'</span><b>'+(ok?'执行成功':'执行失败')+'</b><span style="margin-left:auto">耗时 '+log.dur+'</span></div>'
      +'<pre class="mono" style="background:#0d1424;color:#9fb2d0;border-radius:8px;padding:12px;font-size:11.5px;line-height:1.8;max-height:260px;overflow:auto">'+UI.esc(log.content)+'</pre>'});
  }, 1100);
};
A.scLog = function(id){
  var l = DB.execLogs.find(function(x){return x.id===id;});
  UI.modal({title:'执行日志 - '+l.id, w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.desc([['脚本', l.script],['方式', l.mode],['开始', l.start],['耗时', l.dur],['结果', st(l.status)]])
    + '<pre class="mono" style="background:#0d1424;color:#9fb2d0;border-radius:8px;padding:12px;font-size:11.5px;line-height:1.8;max-height:280px;overflow:auto">'+UI.esc(l.content)+'</pre>'});
};
A.scRerun = function(id){
  var l = DB.execLogs.find(function(x){return x.id===id;});
  var sid = l.script.split(' ')[0];
  UI.confirm({title:'重跑脚本', msg:'重新执行「'+l.script+'」？', detail:'生成新的执行日志。', onOk:function(){
    var d = DB.scripts.find(function(x){return x.id===sid;});
    if(d) d.lastExecFail = false;
    UI.toast('重跑已触发', 'success'); App.resolve();
  }});
};

/* ---- 环境与依赖 ---- */
App.reg('#/script/env', '环境与依赖', function(){
  var html = UI.pageHead('Python 环境与依赖', '虚拟环境隔离管理：Python 版本 / 三方包清单 / 使用脚本数；支持包安装与环境克隆',
    '<button class="btn btn-primary" onclick="A.veCreate()">+ 新建环境</button>');
  html += UI.card('环境列表', UI.tbl({
    id:'t_ve', rowKey:'id', pageSize:8, searchKeys:['id','name'], searchPh:'搜索环境',
    data:function(){ return DB.pyEnvs; },
    cols:[
      {t:'环境', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+' · Python '+r.python+'</div>';}},
      {t:'包清单', render:function(r){return r.pkgs.map(function(p){return '<span class="tag tag-outline" style="margin:1px 3px 1px 0">'+p.n+' '+p.v+'</span>';}).join('');}},
      {t:'使用脚本', k:'used', render:function(r){return r.used+' 个';}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.veAddPkg(\''+r.id+'\')">安装包</a><a onclick="A.veClone(\''+r.id+'\')">克隆</a>'
        +'<a onclick="UI.toggleStatus(DB.pyEnvs.find(function(x){return x.id===\''+r.id+'\'}))">'+(r.status==='enabled'?'停用':'启用')+'</a>';
    }}));
  return html;
});
A.veCreate = function(){
  UI.drawer({title:'新建 Python 环境', body:
    UI.fInput('环境名称', 've_name', {req:true, ph:'如：py3-etl'})
    + UI.fSelect('Python 版本', 've_py', ['3.10.4','3.9.7','3.11.6'], {value:'3.10.4'})
    + '<div class="lock-tip">创建后自动安装 pandas/numpy 基础包；信创环境（鲲鹏920）使用 aarch64 轮子源。</div>',
    onOk:function(){
      var name = UI.val('ve_name');
      if(!name){ UI.toast('请填写环境名称', 'warn'); return false; }
      DB.pyEnvs.push({id:'VENV0'+(DB.pyEnvs.length+1), name:name, python:UI.val('ve_py'), pkgs:[{n:'pandas',v:'2.1.1'},{n:'numpy',v:'1.26.0'}], status:'enabled', used:0});
      UI.toast('环境已创建', 'success');
    }});
};
A.veAddPkg = function(id){
  var d = DB.pyEnvs.find(function(x){return x.id===id;});
  UI.drawer({title:'安装包 - '+d.name, body:
    UI.fInput('包名', 'pk_name', {req:true, ph:'如：scikit-learn'})
    + UI.fInput('版本（可选）', 'pk_v', {ph:'如：1.3.2，留空装最新'})
    + '<div class="lock-tip">pip 安装源：内网镜像（鲲鹏 aarch64），支持离线 whl 包。</div>',
    onOk:function(){
      var n = UI.val('pk_name');
      if(!n){ UI.toast('请填写包名', 'warn'); return false; }
      d.pkgs.push({n:n, v:UI.val('pk_v')||'latest'});
      UI.toast('包 '+n+' 安装成功', 'success');
    }});
};
A.veClone = function(id){
  var d = DB.pyEnvs.find(function(x){return x.id===id;});
  UI.confirm({title:'克隆环境', msg:'克隆「'+d.name+'」为新环境？', onOk:function(){
    DB.pyEnvs.push({id:'VENV0'+(DB.pyEnvs.length+1), name:d.name+'-copy', python:d.python, pkgs:JSON.parse(JSON.stringify(d.pkgs)), status:'enabled', used:0});
    UI.toast('环境已克隆', 'success'); App.resolve();
  }});
};

/* ---- 远程执行 SSH ---- */
App.reg('#/script/remote', '远程执行(SSH)', function(){
  var html = UI.pageHead('远程执行节点（SSH）',
    '脚本可在远程主机执行：SSH 连接管理（密钥/密码加密存储），信创麒麟V10 环境已联测',
    '<button class="btn btn-primary" onclick="A.rnCreate()">+ 添加节点</button>');
  html += UI.card('节点列表', UI.tbl({
    id:'t_rn', rowKey:'id', pageSize:8, searchKeys:['id','name','ip'], searchPh:'搜索节点/IP',
    data:function(){ return DB.remoteNodes; },
    cols:[
      {t:'节点', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+r.os+'</div>';}},
      {t:'IP', k:'ip', render:function(r){return '<span class="mono">'+r.ip+'</span>';}},
      {t:'认证', k:'auth'},
      {t:'最近心跳', k:'lastPing'},
      {t:'脚本数', k:'scripts'},
      {t:'状态', k:'status', render:function(r){return st(r.status==='online'?'success':'failed');}}
    ],
    ops:function(r){
      return '<a onclick="A.rnPing(\''+r.id+'\')">测试连接</a>'
        +'<a onclick="A.rnEdit(\''+r.id+'\')">编辑</a>'
        +'<a class="danger" onclick="UI.delRow(DB.remoteNodes, \'id\', \''+r.id+'\', \''+r.name+'\')">删除</a>';
    }}));
  return html;
});
A.rnFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('节点名称', 'rn_name', {value:d.name, req:true})
    + UI.fInput('IP 地址', 'rn_ip', {value:d.ip, req:true})
    + UI.fInput('SSH 端口', 'rn_port', {value:d.port||22, type:'number'})
    + UI.fSelect('认证方式', 'rn_auth', [{v:'密钥',t:'密钥（推荐）'},{v:'密码',t:'密码（加密存储）'}], {value:(d.auth||'密钥').indexOf('密钥')>=0?'密钥':'密码'})
    + '</div>';
};
A.rnCreate = function(){ UI.drawer({title:'添加远程节点', w:'w-lg', body:A.rnFormFields({}), onOk:function(){
  var name = UI.val('rn_name');
  if(!name||!UI.val('rn_ip')){ UI.toast('请填写节点名称与IP', 'warn'); return false; }
  DB.remoteNodes.push({id:'RN0'+(DB.remoteNodes.length+1), name:name, ip:UI.val('rn_ip'), os:'麒麟V10', mode:'SSH', auth:UI.val('rn_auth')==='密钥'?'密钥(datara_key)':'密码(加密存储)', status:'online', lastPing:now+' 23:30', scripts:0});
  UI.toast('节点已添加，连接测试通过', 'success');}}); };
A.rnEdit = function(id){ var d = DB.remoteNodes.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑节点 - '+d.name, w:'w-lg', body:A.rnFormFields(d), onOk:function(){
    Object.assign(d, {name:UI.val('rn_name'), ip:UI.val('rn_ip')});
    UI.toast('节点已保存', 'success');}}); };
A.rnPing = function(id){
  var d = DB.remoteNodes.find(function(x){return x.id===id;});
  UI.toast('正在 SSH 连接 '+d.ip+' ...', 'info');
  setTimeout(function(){
    if(d.status==='online') UI.toast('连接成功：'+d.os+' · 认证通过 · 耗时 '+(20+Math.floor(Math.random()*80))+' ms', 'success');
    else UI.confirm({title:'连接失败', danger:true, msg:'SSH 连接 '+d.ip+' 超时', detail:'节点最近心跳 '+d.lastPing+'，请检查网络/VPN 通道。'});
  }, 700);
};
})();
