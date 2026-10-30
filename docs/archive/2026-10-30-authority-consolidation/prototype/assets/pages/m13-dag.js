/* ============================================================
   M13 DAG工作流（定义/实例/依赖/告警SLA）
   闭环：草稿 → 上线 → 调度实例 → 失败断点恢复/重跑 → 成功 → SLA统计
   ============================================================ */
(function(){
/* SVG DAG 绘制：按依赖分层布局 */
function dagSvg(nodes, statusMap){
  var levels = {}; var seq = {};
  function depth(n){
    if(levels[n.id]!=null) return levels[n.id];
    levels[n.id] = 0;
    var d = 0;
    (n.dep||[]).forEach(function(pid){
      var p = nodes.find(function(x){return x.id===pid;});
      if(p) d = Math.max(d, depth(p)+1);
    });
    levels[n.id] = d; return d;
  }
  nodes.forEach(depth);
  var maxLv = Math.max.apply(null, nodes.map(function(n){return levels[n.id];}));
  var order = {};
  nodes.forEach(function(n){ order[n.id] = (order[levels[n.id]]=(order[levels[n.id]]||0)+1); });
  var NW=150, NH=48, GX=190, GY=96, H=40+((maxLv+1)*GY), W=80+((maxLv+1)*GX);
  var pos = {};
  var svg = '<svg class="dag-svg" width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#a8b6cc"/></marker></defs>';
  nodes.forEach(function(n){
    var lv = levels[n.id], k = order[n.id];
    pos[n.id] = {x: 40+lv*GX, y: 40+ (k-1)*GY + (maxLv>0? (maxLv*GY*0)/2:0)};
  });
  nodes.forEach(function(n){
    (n.dep||[]).forEach(function(pid){
      var f = pos[pid], t = pos[n.id];
      if(!f||!t) return;
      var x1=f.x+NW, y1=f.y+NH/2, x2=t.x, y2=t.y+NH/2, mx=(x1+x2)/2;
      var cls = 'dag-edge';
      var stt = statusMap && statusMap[pid];
      if(stt==='success') cls+=' ok-edge'; else if(stt==='failed') cls+=' err-edge';
      svg += '<path class="'+cls+'" d="M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2+'"/>';
    });
  });
  nodes.forEach(function(n){
    var p = pos[n.id];
    var stt = statusMap && statusMap[n.id];
    var col = '#242938', sub = n.type;
    if(stt==='success'){ col='#16a34a'; sub='✓ 成功 · '+n.dur; }
    else if(stt==='failed'){ col='#e5484d'; sub='✗ 失败 · 重试'+n.retry; }
    else if(stt==='waiting'){ col='#8c94a6'; sub='等待中'; }
    else if(stt==='running'){ col='#1668dc'; sub='● 运行中'; }
    svg += '<g class="dag-node'+(stt==='failed'?'':'')+'" onclick="A.wfNode(\''+n.id+'\')">'
      +'<rect class="n-box" x="'+p.x+'" y="'+p.y+'" width="'+NW+'" height="'+NH+'" rx="8"/>'
      +'<text x="'+(p.x+14)+'" y="'+(p.y+20)+'" font-size="11.5" font-weight="600" fill="'+col+'">'+UI.esc(n.name)+'</text>'
      +'<text x="'+(p.x+14)+'" y="'+(p.y+37)+'" font-size="10" fill="#8c94a6">'+UI.esc(sub)+'</text></g>';
  });
  svg += '</svg>';
  return svg;
}

/* ---- 工作流定义 ---- */
App.reg('#/dag/list', '工作流定义', function(){
  var html = UI.pageHead('DAG 工作流定义',
    '可视化编排调度：节点依赖 · Cron 调度 · 版本发布 · 失败重试与断点恢复',
    '<button class="btn btn-primary" onclick="A.wfCreate()">+ 新建工作流</button>',
    '操作指引：① 新建工作流生成草稿；② 进入可视化编排，从元件库拖入任务节点并连线（开始→任务→结束）；③ 校验通过后「发布上线」生成调度；④ 上线后可手动运行、下线或重新上线。状态流转见下方状态图；实例失败支持断点恢复与整体重跑。');
  html += UI.stateFlow([
    {k:'draft',   t:'草稿',       d:'编排未发布'},
    {k:'online',  t:'已上线',     d:'调度生效 · 可手动运行'},
    {k:'offline', t:'已下线',     d:'暂停调度 · 可重新上线'}
  ], null, '闭环说明：草稿 →（校验+发布）→ 已上线 →（下线）→ 已下线 →（重新上线）→ 已上线；上线实例失败可断点恢复或整体重跑。');
  html += UI.card('工作流列表', UI.tbl({
    id:'t_wf', rowKey:'id', pageSize:8, searchKeys:['id','name','owner'], searchPh:'搜索工作流',
    filters:[{k:'status', label:'状态', options:[{v:'online',t:'已上线'},{v:'draft',t:'草稿'},{v:'offline',t:'已下线'}]}],
    data:function(){ return DB.workflows; },
    cols:[
      {t:'工作流', k:'name', sortable:true, render:function(r){
        return '<div><a onclick="A.wfDetail(\''+r.id+'\')"><b>'+r.name+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+UI.esc(r.desc)+'</div></div>';}},
      {t:'调度周期', k:'cron', render:function(r){return '<span class="mono" style="font-size:11.5px">'+r.cron+'</span>';}},
      {t:'节点数', k:'nodes'},
      {t:'最近实例', render:function(r){return r.lastRun+' '+st(r.lastResult);}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}},
      {t:'负责人', k:'owner'}
    ],
    ops:function(r){
      return '<a onclick="App.go(\'#/dag/design/'+r.id+'\')">可视化编排</a>'
        +'<a onclick="A.wfDetail(\''+r.id+'\')">画布</a>'
        +(r.status==='draft'? '<a onclick="A.wfPublish(\''+r.id+'\')">发布上线</a>': r.status==='online'? '<a onclick="A.wfRun(\''+r.id+'\')">手动运行</a><a onclick="A.wfOffline(\''+r.id+'\')">下线</a>':'<a onclick="A.wfPublish(\''+r.id+'\')">重新上线</a>')
        +'<a onclick="A.wfEdit(\''+r.id+'\')">编辑</a>'
        +'<a class="danger" onclick="A.wfDel(\''+r.id+'\')">删除</a>';
    }}));
  return html;
});
A.wfFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('工作流名称', 'wf_name', {value:d.name, req:true})
    + UI.fInput('Cron 表达式', 'wf_cron', {value:d.cron||'0 30 2 * * ?', help:' Quartz 格式：秒 分 时 日 月 周'})
    + UI.fSelect('负责人', 'wf_owner', ['王工','李工','张工','赵工','刘工'], {value:d.owner||DB.user.name})
    + UI.fTextarea('描述', 'wf_desc', {value:d.desc, rows:2, full:true})
    + '</div><div class="lock-tip">节点编排：保存后进入画布，添加节点（ETL/SQL/脚本/子工作流/依赖检查）并连线；表级跨流依赖在「依赖管理」配置。</div>';
};
A.wfCreate = function(){ UI.drawer({title:'新建工作流', w:'w-lg', body:A.wfFormFields({}), onOk:function(){
  var name = UI.val('wf_name');
  if(!name){ UI.toast('请填写工作流名称', 'warn'); return false; }
  DB.workflows.push({id:'WF00'+(DB.workflows.length+1), name:name, cron:UI.val('wf_cron'), owner:UI.val('wf_owner'), status:'draft', nodes:0, lastRun:'-', lastResult:'-', desc:UI.val('wf_desc'), nodesDetail:[]});
  UI.toast('工作流已创建（草稿），请在画布中编排节点后发布上线', 'success');
}}); };
A.wfEdit = function(id){ var d = DB.workflows.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑工作流 - '+d.name, w:'w-lg', body:A.wfFormFields(d), onOk:function(){
    Object.assign(d, {name:UI.val('wf_name'), cron:UI.val('wf_cron'), owner:UI.val('wf_owner'), desc:UI.val('wf_desc')});
    UI.toast('工作流已保存', 'success');}}); };
A.wfPublish = function(id){
  var d = DB.workflows.find(function(x){return x.id===id;});
  if(!d.nodesDetail.length){ UI.toast('请先在画布中编排节点', 'warn'); A.wfDetail(id); return; }
  UI.confirm({title:'发布上线', msg:'确认发布工作流「'+d.name+'」？', detail:'上线后按 Cron（'+d.cron+'）自动调度；发布进行版本快照 v1，支持回滚。', onOk:function(){
    d.status = 'online'; UI.toast('工作流已上线，调度生效', 'success'); App.resolve();
  }});
};
A.wfOffline = function(id){
  var d = DB.workflows.find(function(x){return x.id===id;});
  UI.confirm({title:'下线确认', danger:true, msg:'确认下线「'+d.name+'」？', detail:'下线后停止调度；运行中实例将继续执行完成。下游依赖将转为等待。', onOk:function(){
    d.status='offline'; UI.toast('工作流已下线', 'info'); App.resolve();
  }});
};
A.wfRun = function(id){
  var d = DB.workflows.find(function(x){return x.id===id;});
  UI.confirm({title:'手动运行', msg:'立即触发一次「'+d.name+'」实例？', detail:'业务日期默认 T-1（${biz_date}），可在高级参数中覆盖。', onOk:function(){
    var inst = {id:'R'+now.replace(/-/g,'')+'-00'+(DB.wfInstances.length+1), wf:d.id, wfName:d.name, bizDate:'2026-09-11', status:'running', startAt:now+' 23:10', endAt:'-', dur:'-',
      nodes:d.nodesDetail.map(function(n,i){return {id:n.id, name:n.name, status:i===0?'running':'waiting', start:i===0?'23:10:05':'-', end:'-', dur:'-', retry:0};})};
    DB.wfInstances.unshift(inst);
    d.lastRun = inst.startAt; d.lastResult = 'running';
    UI.toast('实例 '+inst.id+' 已触发，正在运行（可在运行实例中监控）', 'success');
    App.go('#/dag/runs');
  }});
};
A.wfDel = function(id){
  var d = DB.workflows.find(function(x){return x.id===id;});
  var dep = DB.tableDeps.some(function(x){return x.down.wf===d.name||x.up.wf===d.name;});
  if(d.status==='online'){ UI.confirm({title:'无法删除', danger:true, msg:'工作流「'+d.name+'」已上线', detail:'请先下线后再删除。'}); return; }
  if(dep){ UI.confirm({title:'无法删除', danger:true, msg:'工作流被跨流依赖引用', detail:'请先在「依赖管理」中解除依赖。'}); return; }
  UI.delRow(DB.workflows, 'id', id, d.name);
};
A.wfNode = function(){ UI.toast('节点操作：配置 / 查看代码 / 运行日志 / 重跑，请在实例详情中使用', 'info'); };

/* ---- 工作流画布详情 ---- */
A.wfDetail = function(id){
  var d = DB.workflows.find(function(x){return x.id===id;});
  UI.drawer({title:'工作流画布 - '+d.name+'（'+d.id+' · '+st(d.status)+'）', w:'w-xl', body:
    '<div class="dag-legend"><span><i class="lg-dot" style="background:#16a34a"></i>成功</span><span><i class="lg-dot" style="background:#e5484d"></i>失败</span><span><i class="lg-dot" style="background:#a8b6cc"></i>依赖</span>'
    +'<span style="margin-left:auto"><a onclick="A.wfAddNode(\''+d.id+'\')">+ 添加节点</a></span></div>'
    +'<div class="dag-wrap" style="overflow:auto">'+ (d.nodesDetail.length? dagSvg(d.nodesDetail) : '<div class="empty"><span class="e-ico">⑃</span><p>暂无节点，请添加</p></div>') +'</div>'
    + '<div class="card-head" style="border-bottom:none;padding:12px 0 6px"><h3>节点清单</h3></div>'
    + UI.tbl({id:'t_wfn', rowKey:'id', pageSize:6, searchKeys:['name','type'], data:function(){return d.nodesDetail;},
      cols:[{t:'节点', k:'name'},{t:'类型', k:'type'},{t:'依赖', render:function(r){return (r.dep||[]).join('、')||'-';}},
            {t:'产出表', k:'outTable', render:function(r){return '<span class="mono">'+r.outTable+'</span>';}},
            {t:'重试', k:'retry'},{t:'耗时', k:'dur'}],
      ops:function(n){ return '<a onclick="UI.toast(\'节点配置：超时/重试/参数（原型演示）\',\'info\')">配置</a><a class="danger" onclick="A.wfDelNode(\''+d.id+'\',\''+n.id+'\')">移除</a>'; }}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">关闭</button>'+(d.status==='online'?'<button class="btn btn-primary" onclick="UI.closeDrawer();A.wfRun(\''+d.id+'\')">手动运行</button>':'<button class="btn btn-primary" onclick="UI.closeDrawer();A.wfPublish(\''+d.id+'\')">发布上线</button>')});
};
A.wfAddNode = function(id){
  var d = DB.workflows.find(function(x){return x.id===id;});
  UI.drawer({title:'添加节点 - '+d.name, w:'w-lg', body:
    UI.fInput('节点名称', 'wn_name', {req:true, ph:'如：支付日汇总'})
    + UI.fSelect('节点类型', 'wn_type', [{v:'ETL节点',t:'ETL节点（引用ETL任务）'},{v:'SQL节点',t:'SQL节点（在线SQL）'},{v:'脚本节点',t:'脚本节点（引用脚本库）'},{v:'子工作流',t:'子工作流节点'},{v:'依赖检查',t:'依赖检查（表级依赖）'}], {})
    + UI.fSelect('产出表', 'wn_out', DB.metaTables.map(function(t){return {v:t.name,t:t.name};}).concat([{v:'-',t:'（无产出）'}]), {})
    + UI.fInput('重试次数', 'wn_retry', {value:'2', type:'number'})
    + UI.fSelect('依赖节点（多选同上游）', 'wn_dep', d.nodesDetail.map(function(n){return {v:n.id, t:n.name};}), {value:d.nodesDetail.length? d.nodesDetail[d.nodesDetail.length-1].id : ''}),
    onOk:function(){
      var name = UI.val('wn_name');
      if(!name){ UI.toast('请填写节点名称', 'warn'); return false; }
      var nid = 'n'+(d.nodesDetail.length+1);
      d.nodesDetail.push({id:nid, name:name, type:UI.val('wn_type'), dep:UI.val('wn_dep')?[UI.val('wn_dep')]:[], outTable:UI.val('wn_out'), retry:+UI.val('wn_retry')||0, dur:'-'});
      d.nodes = d.nodesDetail.length;
      UI.toast('节点已添加，可继续编排或发布', 'success'); UI.closeDrawer(); A.wfDetail(id);
      return false;
    }});
};
A.wfDelNode = function(wid, nid){
  var d = DB.workflows.find(function(x){return x.id===wid;});
  var used = d.nodesDetail.some(function(n){return (n.dep||[]).indexOf(nid)>=0;});
  if(used){ UI.confirm({title:'无法移除', danger:true, msg:'该节点被其他节点依赖', detail:'请先移除下游节点的依赖。'}); return; }
  UI.confirm({title:'移除节点', danger:true, msg:'确认移除该节点？', onOk:function(){
    d.nodesDetail = d.nodesDetail.filter(function(n){return n.id!==nid;});
    d.nodes = d.nodesDetail.length; UI.closeDrawer(); UI.toast('节点已移除', 'info'); A.wfDetail(wid);
  }});
};

/* ---- 运行实例 ---- */
App.reg('#/dag/runs', '运行实例', function(){
  var html = UI.pageHead('运行实例',
    '调度实例监控：节点级状态/耗时/重试，失败实例支持断点恢复（从失败节点续跑）与整体重跑',
    '<button class="btn" onclick="UI.toast(\'已刷新实例状态\',\'info\');App.resolve()">刷新</button>');
  html += '<div class="grid grid-4" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#1668dc">⑃</span><div><div class="stat-num">'+DB.wfInstances.length+'</div><div class="stat-label">实例总数（近2日）</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+DB.wfInstances.filter(function(i){return i.status==='success';}).length+'</div><div class="stat-label">成功</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#e5484d">✗</span><div><div class="stat-num">'+DB.wfInstances.filter(function(i){return i.status==='failed';}).length+'</div><div class="stat-label">失败待恢复</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#0891b2">●</span><div><div class="stat-num">'+DB.wfInstances.filter(function(i){return i.status==='running';}).length+'</div><div class="stat-label">运行中</div></div></div></div>';
  html += UI.card('实例列表', UI.tbl({
    id:'t_wfi', rowKey:'id', pageSize:8, searchKeys:['id','wfName'], searchPh:'搜索实例/工作流',
    filters:[{k:'status', label:'状态', options:[{v:'success',t:'成功'},{v:'failed',t:'失败'},{v:'running',t:'运行中'},{v:'waiting',t:'等待'}]}],
    data:function(){ return DB.wfInstances; },
    cols:[
      {t:'实例', k:'id', render:function(r){return '<a onclick="A.wfiDetail(\''+r.id+'\')"><b>'+r.id+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.wfName+'</div>';}},
      {t:'业务日期', k:'bizDate'},
      {t:'开始', k:'startAt'},{t:'结束', k:'endAt'},{t:'耗时', k:'dur'},
      {t:'节点进度', render:function(r){
        var ok = r.nodes.filter(function(n){return n.status==='success';}).length;
        var pct = Math.round(ok/r.nodes.length*100);
        return '<div class="progress'+(r.status==='failed'?' red':' green')+'" style="width:110px"><div class="bar" style="width:'+pct+'%"></div></div><div style="font-size:11px;color:var(--text-3)">'+ok+'/'+r.nodes.length+'</div>';}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.wfiDetail(\''+r.id+'\')">详情</a>'
        +(r.status==='failed'? '<a onclick="A.wfiResume(\''+r.id+'\')">断点恢复</a><a onclick="A.wfiRerun(\''+r.id+'\')">整体重跑</a>':'')
        +(r.status==='running'? '<a class="danger" onclick="A.wfiKill(\''+r.id+'\')">终止</a>':'');
    }}));
  return html;
});
A.wfiDetail = function(id){
  var r = DB.wfInstances.find(function(x){return x.id===id;});
  var wf = DB.workflows.find(function(w){return w.id===r.wf;});
  var sm = {}; r.nodes.forEach(function(n){ sm[n.id]=n.status; });
  var gantt = r.nodes.map(function(n){
    var w = n.dur==='-'? 6 : Math.min(46, parseFloat(n.dur)*0.5+6);
    var c = n.status==='success'?'#16a34a':n.status==='failed'?'#e5484d':n.status==='running'?'#1668dc':'#cdd5e3';
    return '<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;font-size:11.5px"><span style="width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+UI.esc(n.name)+'</span><div style="flex:1"><div style="height:14px;border-radius:3px;background:'+c+';width:'+w+'%"></div></div><span style="color:var(--text-3);width:64px">'+n.start+(n.dur!=='-'?' · '+n.dur:'')+'</span></div>';
  }).join('');
  UI.drawer({title:'实例详情 - '+r.id+'（'+r.wfName+' · 业务日期 '+r.bizDate+'）', w:'w-xl', body:
    UI.desc([['实例ID', r.id],['工作流', r.wfName],['业务日期', r.bizDate],['开始', r.startAt],['结束', r.endAt],['状态', st(r.status)]])
    + '<div class="dag-legend"><span>执行 DAG（点击节点查看日志）</span></div>'
    + '<div class="dag-wrap" style="overflow:auto;max-height:300px">'+dagSvg(wf?wf.nodesDetail:r.nodes.map(function(n){return {id:n.id,name:n.name,dep:[],type:''};}), sm)+'</div>'
    + '<div class="card-head" style="border-bottom:none;padding:12px 0 6px"><h3>节点甘特</h3></div>'+gantt,
    footer:'<button class="btn" onclick="UI.closeDrawer()">关闭</button>'
      +(r.status==='failed'?'<button class="btn btn-primary" onclick="UI.closeDrawer();A.wfiResume(\''+r.id+'\')">断点恢复</button>':'')
      +'<button class="btn" onclick="A.wfiLog(\''+r.id+'\')">失败日志</button>'});
  A._curInst = r;
};
A.wfiLog = function(id){
  var r = DB.wfInstances.find(function(x){return x.id===id;});
  var fn = r.nodes.find(function(n){return n.status==='failed';});
  UI.modal({title:'节点失败日志 - '+(fn?fn.name:'-'), w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    '<div class="mono" style="background:#0d1424;color:#9fb2d0;border-radius:8px;padding:14px;font-size:11.5px;line-height:1.9">'
    +'['+r.startAt+'] INFO  节点启动：'+(fn?UI.esc(fn.name):'-')+'（重试 '+ (fn?fn.retry:0) +' 次）<br>'
    +'['+r.startAt+'] ERROR SQL错误 [1105]: errCode = 2, detailMessage = Unknown column \'pay_channel\' in \'dwd_order_pay_detail\'<br>'
    +'['+r.startAt+'] WARN  根因建议：模型 v5 已增加 pay_channel 字段（M04），请检查执行环境表结构是否已物理化同步<br>'
    +'['+r.startAt+'] WARN  已触发工作流失败告警（DA01 邮件+短信），下游 2 节点等待中</div>'
    +'<div class="banner banner-warn" style="margin-top:10px"><span class="b-ico">⚠</span><span>修复建议：到 <a onclick="UI.closeModal();App.go(\'#/model/list\')">数仓建模</a> 对 dwd_order_pay_detail 执行「物理化同步」，或到 <a onclick="UI.closeModal();App.go(\'#/ide\')">IDE</a> 手工补齐字段后断点恢复。</span></div>'});
};
A.wfiResume = function(id){
  var r = DB.wfInstances.find(function(x){return x.id===id;});
  var fn = r.nodes.find(function(n){return n.status==='failed';});
  UI.confirm({title:'断点恢复', msg:'从失败节点「'+(fn?fn.name:'-')+'」续跑？', detail:'成功节点不重跑；恢复后下游等待节点继续执行。', onOk:function(){
    fn.status='success'; fn.retry=0; fn.dur='38s'; fn.end='23:15:20';
    r.nodes.forEach(function(n, i){
      if(n.status==='waiting'){ n.status='success'; n.start='23:15:21'; n.end='23:1'+(6+i)+':10'; n.dur=(30+i*5)+'s'; }
    });
    r.status='success'; r.endAt=now+' 23:17'; r.dur='46m';
    var wf = DB.workflows.find(function(w){return w.id===r.wf;}); if(wf) wf.lastResult='success';
    UI.toast('断点恢复完成：全部节点成功，实例已置为成功', 'success'); App.resolve();
  }});
};
A.wfiRerun = function(id){
  var r = DB.wfInstances.find(function(x){return x.id===id;});
  UI.confirm({title:'整体重跑', danger:true, msg:'确认重跑整个实例 '+r.id+'？', detail:'全部分区将覆盖重算，请确认下游消费方无影响。', onOk:function(){
    r.nodes.forEach(function(n){ n.status='success'; if(n.start==='-') n.start='23:18:00'; n.end='23:20:00'; if(n.dur==='-') n.dur='40s'; n.retry=0; });
    r.status='success'; r.endAt=now+' 23:20'; r.dur='50m';
    UI.toast('重跑完成，实例成功', 'success'); App.resolve();
  }});
};
A.wfiKill = function(id){
  var r = DB.wfInstances.find(function(x){return x.id===id;});
  UI.confirm({title:'终止实例', danger:true, msg:'确认终止运行中的实例 '+r.id+'？', detail:'运行中节点将被 kill，剩余节点标记为已终止。', onOk:function(){
    r.nodes.forEach(function(n){ if(n.status!=='success') n.status='killed'; });
    r.status='killed';
    UI.toast('实例已终止（状态：已终止），可整体重跑', 'info'); App.resolve();
  }});
};

/* ---- 依赖管理 ---- */
App.reg('#/dag/depend', '依赖管理', function(){
  var html = UI.pageHead('跨工作流依赖管理',
    '表级依赖：下游任务通过「依赖检查节点」等待上游工作流产出表就绪，避免数据未就绪先跑',
    '<button class="btn btn-primary" onclick="A.tdCreate()">+ 新建表依赖</button>');
  html += '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>周期对齐：T-1 表示依赖上游昨日分区（dt=${biz_date}），校验策略支持「等待完成 / 校验分区行数>0」。</span></div>';
  html += UI.card('依赖清单', UI.tbl({
    id:'t_td', rowKey:'id', pageSize:8, searchKeys:['id','table'], data:function(){
      return DB.tableDeps.map(function(d,i){ return Object.assign({id:'TD0'+(i+1)}, d); }); },
    cols:[
      {t:'下游任务', render:function(r){return '<b>'+r.down.task+'</b><div style="font-size:11px;color:var(--text-3)">'+r.down.wf+'</div>';}},
      {t:'依赖表', render:function(r){return '<span class="mono" style="color:var(--primary)">'+r.table+'</span>';}},
      {t:'上游产出', render:function(r){return r.up.task+'<div style="font-size:11px;color:var(--text-3)">'+r.up.wf+'</div>';}},
      {t:'周期', k:'period', render:function(r){return tag(r.period, r.period==='T-1'?'purple':'blue');}},
      {t:'策略', k:'strategy'},
      {t:'校验状态', k:'check'}
    ],
    ops:function(r){
      return '<a onclick="A.tdCheck(\''+r.table+'\')">校验就绪</a><a class="danger" onclick="A.tdDel(\''+r.table+'\')">解除</a>';
    }}));
  return html;
});
A.tdCreate = function(){
  UI.drawer({title:'新建表依赖', w:'w-lg', body:
    UI.fSelect('下游工作流', 'td_down', DB.workflows.map(function(w){return {v:w.name,t:w.name};}), {})
    + UI.fSelect('依赖表（上游产出）', 'td_table', DB.metaTables.map(function(t){return {v:t.name,t:t.name};}), {})
    + UI.fSelect('周期对齐', 'td_period', [{v:'T-1',t:'T-1（昨日分区）'},{v:'T',t:'T（今日实时）'}], {value:'T-1'})
    + UI.fSelect('等待策略', 'td_strategy', [{v:'等待完成',t:'等待上游工作流完成'},{v:'校验行数',t:'校验分区行数>0'}], {value:'等待完成'}),
    onOk:function(){
      var wf = DB.workflows.find(function(w){return w.name===UI.val('td_down');});
      DB.tableDeps.push({down:{wf:UI.val('td_down'), task:(wf&&wf.nodesDetail[0])?wf.nodesDetail[0].name:'首节点'}, up:{wf:'上游工作流', task:'自动识别产出'}, table:UI.val('td_table'), period:UI.val('td_period'), strategy:UI.val('td_strategy'), check:'待校验'});
      UI.toast('表依赖已创建，下游实例调度时将先执行就绪校验', 'success');
    }});
};
A.tdCheck = function(table){
  UI.toast('正在校验 '+table+' 分区 dt=2026-09-11 ...', 'info');
  setTimeout(function(){ UI.toast('校验通过：分区存在且行数 > 0，下游可执行', 'success'); }, 800);
};
A.tdDel = function(table){
  UI.confirm({title:'解除依赖', danger:true, msg:'确认解除对「'+table+'」的依赖？', detail:'解除后下游调度将不再等待上游产出，可能导致数据未就绪。', onOk:function(){
    DB.tableDeps = DB.tableDeps.filter(function(d){return d.table!==table;});
    UI.toast('依赖已解除', 'info'); App.resolve();
  }});
};

/* ---- 告警与SLA ---- */
App.reg('#/dag/alarm', '告警与SLA', function(){
  var html = UI.pageHead('调度告警与 SLA', '工作流失败/恢复/超时告警策略 + SLA 产出时限监控（今日达标 2/3）',
    '<button class="btn btn-primary" onclick="A.daCreate()">+ 新建告警策略</button>');
  html += UI.card('SLA 产出时限', UI.tbl({
    id:'t_sla', rowKey:'id', pageSize:6, searchKeys:['id','wf'], data:function(){return DB.slaRules;},
    cols:[
      {t:'SLA规则', k:'id', render:function(r){return '<b>'+r.id+'</b>';}},
      {t:'工作流', k:'wf'},
      {t:'产出时限', k:'deadLine'},
      {t:'今日状态', render:function(r){return st(r.status);}},
      {t:'今日情况', k:'today'},
      {t:'达标率', k:'history', render:function(r){return '<span style="font-size:11.5px">'+r.history+'</span>';}}
    ],
    ops:function(r){ return '<a onclick="UI.toast(\'SLA规则编辑（原型演示）：调整时限与升级策略\',\'info\')">编辑</a>'; }}));
  html += UI.card('调度告警策略', UI.tbl({
    id:'t_da', rowKey:'id', pageSize:6, searchKeys:['id','name','scope'], searchPh:'搜索策略',
    data:function(){ return DB.dagAlarms; },
    cols:[
      {t:'策略', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+'</div>';}},
      {t:'范围', k:'scope'},{t:'触发事件', k:'event'},
      {t:'渠道', k:'channel', render:function(r){return r.channel.split('+').map(function(c){return tag(c,'blue');}).join(' ');}},
      {t:'接收人', k:'receivers'},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="UI.toast(\'编辑策略：范围/事件/渠道（原型演示）\',\'info\')">编辑</a>'
        +'<a onclick="UI.toggleStatus(DB.dagAlarms.find(function(x){return x.id===\''+r.id+'\'}))">'+(r.status==='enabled'?'停用':'启用')+'</a>';
    }}));
  return html;
});
A.daCreate = function(){
  UI.drawer({title:'新建调度告警策略', w:'w-lg', body:
    UI.fInput('策略名称', 'da_name', {req:true})
    + UI.fInput('生效范围', 'da_scope', {value:'所有工作流'})
    + UI.fSelect('触发事件', 'da_event', [{v:'节点最终失败',t:'节点最终失败'},{v:'恢复运行/自动续跑完成',t:'断点恢复通知'},{v:'工作流整体超时',t:'SLA 超时'}], {})
    + UI.fCheckGroup('通知渠道', 'da_ch', [{v:'邮件',t:'邮件'},{v:'短信',t:'短信'},{v:'飞书',t:'飞书'}], ['邮件'])
    + UI.fInput('接收人', 'da_recv', {value:'王工/任务负责人'}),
    onOk:function(){
      if(!UI.val('da_name')){ UI.toast('请填写策略名称', 'warn'); return false; }
      DB.dagAlarms.push({id:'DA0'+(DB.dagAlarms.length+1), name:UI.val('da_name'), scope:UI.val('da_scope'), event:UI.val('da_event'), channel:UI.checkVals('da_ch').join('+')||'邮件', receivers:UI.val('da_recv'), status:'enabled'});
      UI.toast('告警策略已创建', 'success');
    }});
};

/* ============================================================
   可视化编排编辑器（DolphinScheduler 式三栏：#/dag/design/:id）
   左：调度任务元件库（拖拽入画布） 中：VC 画布 右：验证与测试
   顶栏：返回 / 工作流名 / 保存 / 校验 / 试运行 / 发布上线
   ============================================================ */
A.DAG_PALETTE = [
  {cat:'通用', items:[
    {type:'shell', name:'SHELL', icon:'❯', color:'#7c3aed', desc:'Shell脚本', summary:'在 Worker 上执行 Shell 脚本'},
    {type:'sql', name:'SQL', icon:'⌨', color:'#334155', desc:'在线SQL加工', summary:'选择数据源执行 SQL，支持查询/非查询与前置后置 SQL'},
    {type:'python', name:'PYTHON', icon:'≽', color:'#0ea5e9', desc:'Python脚本', summary:'在 Worker 上执行 Python 脚本'},
    {type:'subwf', name:'子工作流', icon:'⑃', color:'#8b5cf6', desc:'SUB_PROCESS', summary:'调度其他已上线工作流作为子流程，父流程等待完成'},
    {type:'proc', name:'存储过程', icon:'ƒ', color:'#2563eb', desc:'PROCEDURE', summary:'调用目标库存储过程（CALL proc（参数））'},
    {type:'http', name:'HTTP', icon:'⇄', color:'#0891b2', desc:'HTTP请求', summary:'调用 HTTP 接口（GET/POST），用于服务触发与回调'},
    {type:'spark', name:'SPARK', icon:'✦', color:'#e39316', desc:'Spark任务', summary:'提交 Spark 作业（jar/python），支持 yarn-cluster'},
    {type:'flink', name:'FLINK', icon:'≋', color:'#16a34a', desc:'Flink任务', summary:'提交 Flink 作业（流/批），支持 Savepoint'},
    {type:'mr', name:'MapReduce', icon:'▤', color:'#d97706', desc:'MR任务', summary:'提交 Hadoop MapReduce 作业'}]},
  {cat:'数据集成', items:[
    {type:'datax', name:'DataX', icon:'⇉', color:'#1668dc', desc:'异构同步', summary:'DataX 全量/增量异构数据源同步'},
    {type:'sqoop', name:'SQOOP', icon:'⇷', color:'#059669', desc:'RDBMS⇄Hive', summary:'关系库与 Hive/HDFS 间导入导出'},
    {type:'seatunnel', name:'SeaTunnel', icon:'≋', color:'#7c3aed', desc:'流批同步', summary:'SeaTunnel 流批一体数据集成'},
    {type:'sync', name:'平台同步', icon:'⇄', color:'#0ea5e9', desc:'引用M05同步', summary:'引用批量同步任务（M05 批处理），调度时触发并等待完成'}]},
  {cat:'逻辑控制', items:[
    {type:'depwait', name:'依赖 DEPENDENT', icon:'⛓', color:'#94a3b8', desc:'跨流依赖dep线', summary:'等待其他工作流产出表就绪后再执行（依赖线）'},
    {type:'if', name:'条件 CONDITIONS', icon:'◆', color:'#f59e0b', desc:'条件分支', summary:'按条件走不同分支（分支线，label 自动标注 成功/失败）'},
    {type:'case', name:'切换 SWITCH', icon:'◈', color:'#f59e0b', desc:'多路分支', summary:'多条件多路分支，每条分支线自动标注 分支N'}]},
  {cat:'平台集成', items:[
    {type:'etl', name:'ETL 任务', icon:'⑃', color:'#16a34a', desc:'引用已发布ETL', summary:'引用可视化ETL设计器产出的已发布任务（M05）'},
    {type:'script', name:'脚本库', icon:'❯', color:'#7c3aed', desc:'引用M14脚本', summary:'调用脚本库脚本（Python/Shell），远程执行走执行节点'}]},
  {cat:'云与机器学习', items:[
    {type:'k8s', name:'K8S', icon:'☸', color:'#1668dc', desc:'K8S提交', summary:'向 Kubernetes 提交作业（原型演示）'},
    {type:'zeppelin', name:'ZEPPELIN', icon:'Ⓩ', color:'#0ea5e9', desc:'Notebook', summary:'调用 Zeppelin Notebook 段执行（原型演示）'}]},
  {cat:'系统节点', items:[
    {type:'start', name:'开始', icon:'▶', color:'#16a34a', desc:'流程入口', summary:'工作流入口（固定节点）'},
    {type:'end', name:'结束', icon:'■', color:'#94a3b8', desc:'流程出口', summary:'工作流出口（固定节点）'}]}
];
A.dagTypeName = {sql:'SQL', shell:'SHELL', python:'PYTHON', http:'HTTP', spark:'SPARK', flink:'FLINK', mr:'MapReduce',
  datax:'DataX', sqoop:'SQOOP', seatunnel:'SeaTunnel', k8s:'K8S', zeppelin:'ZEPPELIN',
  sync:'数据同步', etl:'ETL节点', script:'脚本节点', proc:'存储过程', depwait:'依赖检查', if:'判定IF', case:'多路分支CASE', subwf:'子工作流'};
A.dagMeta = function(t){
  var map = {'ETL节点':{type:'etl',icon:'⑃',color:'#16a34a',desc:'引用已发布ETL'}, 'SQL节点':{type:'sql',icon:'⌨',color:'#334155',desc:'SQL加工'}, 'SQL':{type:'sql',icon:'⌨',color:'#334155',desc:'SQL加工'},
    '脚本节点':{type:'script',icon:'❯',color:'#7c3aed',desc:'引用M14脚本'}, '子工作流':{type:'subwf',icon:'⑃',color:'#8b5cf6',desc:'嵌套工作流'},
    '依赖检查':{type:'depwait',icon:'⛓',color:'#94a3b8',desc:'跨流依赖（dep线）'}, '数据同步':{type:'sync',icon:'⇄',color:'#0ea5e9',desc:'引用M05同步'},
    '存储过程':{type:'proc',icon:'ƒ',color:'#2563eb',desc:'CALL调用'}, '判定IF':{type:'if',icon:'◆',color:'#f59e0b',desc:'条件分支'}, '多路分支CASE':{type:'case',icon:'◈',color:'#f59e0b',desc:'多路分支'}};
  return map[t]||{type:'sql',icon:'⌨',color:'#334155',desc:'SQL加工'};
};

/* nodesDetail → VC 画布数据（默认含开始/结束，依赖 → 顺序线） */
A.dagFlow = function(d){
  if(d.flow && d.flow.nodes && d.flow.nodes.length) return d.flow;
  var nodes = [{id:'start', name:'开始', type:'start', icon:'▶', color:'#16a34a', x:30, y:160, cat:'系统', summary:'工作流入口（固定节点）', cfg:{}},
    {id:'end', name:'结束', type:'end', icon:'■', color:'#94a3b8', x:940, y:160, cat:'系统', summary:'工作流出口（固定节点）', cfg:{}}];
  var edges = [];
  var tasks = d.nodesDetail||[];
  tasks.forEach(function(n){
    var m = A.dagMeta(n.type);
    nodes.push({id:n.id, name:n.name, type:m.type, icon:m.icon, color:m.color, cat:'调度任务',
      summary:(m.desc||'调度任务')+(n.outTable && n.outTable!=='-'? ' · 产出 '+n.outTable : ''),
      cfg:{'重试次数':String(n.retry||0), '耗时':n.dur||'-', '产出表':(n.outTable && n.outTable!=='-')? n.outTable : ''}});
  });
  tasks.forEach(function(n){
    (n.dep||[]).forEach(function(pid){
      if(tasks.some(function(t){return t.id===pid;})) edges.push({from:pid, to:n.id, kind:'flow'});
    });
  });
  tasks.forEach(function(n){
    if(!edges.some(function(e){return e.to===n.id;})) edges.push({from:'start', to:n.id, kind:'flow'});
    if(!edges.some(function(e){return e.from===n.id;})) edges.push({from:n.id, to:'end', kind:'flow'});
  });
  if(!tasks.length) edges.push({from:'start', to:'end', kind:'flow'});
  VC.autoPos(nodes, edges);
  return {nodes:nodes, edges:edges};
};

App.reg('#/dag/design/:id', '可视化编排', function(p){
  var d = DB.workflows.find(function(x){return x.id===p.id;});
  if(!d) return '<div class="empty">工作流不存在</div>';
  A._dagCur = d;
  /* DolphinScheduler 式顶栏：名称区（复制名称/查看变量/上线标签） + 右侧工具区 */
  var head = '<div class="etl-topbar">'
    + '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
    + '<a onclick="App.go(\'#/dag/list\')">←</a>'
    + '<b style="font-size:14.5px" id="dagWfName">'+UI.esc(d.name)+'</b>'
    + '<span class="vc-tool" style="position:static" title="复制名称" onclick="A.dagCopyName()">⧉</span>'
    + '<span class="vc-tool" style="position:static" title="查看变量" onclick="A.dagVars()">∴</span>'
    + st(d.status)
    + '<span class="mono" style="color:var(--text-3);font-size:11.5px">'+d.id+' · Cron <span id="dagCronTxt">'+UI.esc(d.cron)+'</span> · 负责人 '+UI.esc(d.owner)+'</span></div>'
    + '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">'
    + '<select id="dagNodeSel" onchange="A.dagFocusNode(this.value)" style="padding:4px 8px;border:1px solid var(--border-strong);border-radius:7px;font-size:12px;background:#fff;max-width:150px"><option value="">搜索节点…</option>'
    +   '<option value="start">开始</option><option value="end">结束</option>'
    +   (d.nodesDetail||[]).map(function(n){return '<option value="'+n.id+'">'+UI.esc(n.name)+'</option>';}).join('')+'</select>'
    + '<button class="btn btn-sm" title="下载工作流图片" onclick="UI.toast(\'工作流图片已下载：'+d.id+'.png（画布快照）\',\'success\')">⇩ PNG</button>'
    + '<button class="btn btn-sm" title="进入全屏" onclick="A.dagFullscreen()">⛶ 全屏</button>'
    + '<select onchange="A.dagLayout(this.value)" style="padding:4px 8px;border:1px solid var(--border-strong);border-radius:7px;font-size:12px;background:#fff">'
    +   '<option value="">布局类型</option><option value="grid">网格布局</option><option value="dagre">层次布局</option></select>'
    + '<button class="btn btn-sm" title="刷新DAG状态" onclick="A.dagRefreshStatus()">↻ 刷新DAG状态</button>'
    + '<button class="btn btn-sm" onclick="A.dagTiming()">⏱ 定时管理</button>'
    + '<button class="btn btn-sm" onclick="A.dagVersions()">≡ 版本管理</button>'
    + '<button class="btn btn-sm" onclick="A.dagSaveDlg()">保存</button>'
    + (d.status==='online'? '<button class="btn btn-sm" onclick="A.wfOffline(\''+d.id+'\')">下线</button>'
      : '<button class="btn btn-sm btn-success" onclick="A.dagPublish()">发布上线</button>')
    + '</div></div>';
  return head
    + '<div class="etl-main" id="dagEditMain">'
    + '<div id="wfVcMount"></div>'
    + '<div class="etl-right">'
    + '<div class="etl-right-h">验证与测试</div>'
    + '<div class="etl-right-b">'
    + '<div id="wfValidateBox"><div class="f-help" style="margin-bottom:8px">点击「✓ 校验」检查：孤立节点 / 环路 / 断链 / 汇聚语义。</div></div>'
    + '<div style="border-top:1px dashed var(--border);margin:10px 0"></div>'
    + '<b style="font-size:12px">试运行</b>'
    + '<div style="display:flex;gap:6px;margin:8px 0"><button class="btn btn-sm btn-primary" onclick="A.dagDryRun()">▶ 运行</button>'
    + '<button class="btn btn-sm" onclick="A.dagRunFrom()">从指定节点运行</button></div>'
    + '<div class="log-box" style="height:180px" id="wfRunLog"><span class="lg-info">ℹ 尚未执行。点击「▶ 运行」按拓扑序逐节点点亮预演；右键节点可选「从此节点运行」。</span></div>'
    + '</div></div></div>';
});

A.dagInitVc = function(){
  var d = A._dagCur;
  if(!d || !document.getElementById('wfVcMount')) return;
  var f = A.dagFlow(d);
  A._wfVc = VC.create({mount:'wfVcMount', nodes:f.nodes, edges:f.edges, palette:A.DAG_PALETTE, editable:true, height:620,
    legendExtra:[{c:'#16a34a', t:'开始（固定）'}, {c:'#94a3b8', t:'结束（固定）'}],
    onNodeClick:function(n, api){ A.dagNodeEdit(n, api); },
    onNodeContext:function(n, api){ A.dagCtxMenu(n, api); },
    onCanvasChange:function(){ A.dagCanvasChange(); }});
  setTimeout(function(){ A.dagCanvasChange(); }, 60);
};
App.onAfterRender(function(){ if(location.hash.indexOf('#/dag/design/')===0) A.dagInitVc(); });

/* ---- DS 式顶栏交互 ---- */
A.dagCopyName = function(){
  var t = document.createElement('textarea'); t.value = A._dagCur.name; document.body.appendChild(t);
  t.select(); try{ document.execCommand('copy'); }catch(e){}
  t.remove(); UI.toast('复制成功：'+A._dagCur.name, 'success');
};
A.dagVars = function(){
  var g = A._dagCur.globals || [{k:'biz_date', v:'$[yyyy-MM-dd-1]', d:'业务日期（T-1）'}, {k:'hour', v:'$[HH]', d:'执行小时'}];
  UI.modal({title:'参数变量（全局参数）', w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.tbl({id:'t_dagvars', rowKey:'k', pageSize:6, data:function(){ return g; },
      cols:[{t:'键', k:'k', render:function(r){return '<b class="mono">${'+r.k+'}</b>';}},
        {t:'值', k:'v', render:function(r){return '<span class="mono">'+UI.esc(r.v)+'</span>';}},
        {t:'说明', k:'d'}]})});
};
A.dagFocusNode = function(id){
  if(!id || !A._wfVc) return;
  VC.highlight(A._wfVc, id);
  UI.toast('已定位并高亮节点（画布内）', 'info');
};
A.dagFullscreen = function(){
  var m = document.getElementById('dagEditMain');
  if(!m) return;
  if(document.fullscreenElement){ document.exitFullscreen(); }
  else if(m.requestFullscreen){ m.requestFullscreen(); UI.toast('已进入全屏（Esc 退出）','info'); }
};
A.dagLayout = function(mode){
  if(!mode || !A._wfVc) return;
  VC.layout(A._wfVc);
  UI.toast(mode==='grid'? '已应用网格布局':'已应用层次布局（dagre 拓扑分层）', 'success');
};
A.dagRefreshStatus = function(){
  var d = A._dagCur;
  var d0 = VC.getData(A._wfVc);
  d0.nodes.forEach(function(n){ VC.updateNode(A._wfVc, n.id, {status:null}); });
  UI.toast('DAG 状态已刷新：'+d.name+' 最近实例 '+st(d.lastResult||'success')+'（'+(d.lastRun||'-')+'）', 'info');
  setTimeout(A.dagCanvasChange, 50);
};
A.dagRunFrom = function(){
  var sel = document.getElementById('dagNodeSel');
  var id = sel && sel.value;
  if(!id){ UI.toast('请先在「搜索节点」下拉中选择起始节点', 'warn'); return; }
  UI.toast('已从指定节点「'+id+'」向后执行（原型演示：实际按拓扑序仅执行该节点及下游）', 'info');
  A.dagDryRun();
};
/* 节点右键菜单（DolphinScheduler：编辑/复制/删除/查看日志/从此节点运行/向后执行） */
A.dagCtxMenu = function(n, api){
  var old = document.getElementById('dagCtxMenu'); if(old) old.remove();
  var isSys = n.type==='start'||n.type==='end';
  var item = function(fn, label, cls){
    return '<div class="dag-ctx-item'+(cls? ' '+cls:'')+'" onclick="'+fn+'">'+label+'</div>';
  };
  var pop = document.createElement('div');
  pop.id = 'dagCtxMenu'; pop.className = 'dag-ctx';
  pop.innerHTML = item('A.dagNodeEdit(\''+n.id+'\', A._dagApiOf(\''+n.id+'\'));A.dagCtxClose()', '编辑', 'pri')
    + (isSys? '' : item('A.dagNodeCopy(\''+n.id+'\');A.dagCtxClose()', '复制节点'))
    + item('A.dagRunNode(\''+n.id+'\');A.dagCtxClose()', '从此节点运行')
    + item('A.dagRunAfter(\''+n.id+'\');A.dagCtxClose()', '向后执行')
    + item('UI.toast(\'查看日志：'+UI.esc(n.name)+' 最近一次运行日志（原型演示）\',\'info\');A.dagCtxClose()', '查看日志')
    + item('A.dagNodeDel(\''+n.id+'\');A.dagCtxClose()', '删除', 'danger');
  document.body.appendChild(pop);
  var r = document.getElementById((A._wfVc||'')+'_n_'+n.id);
  var rect = r? r.getBoundingClientRect() : {left:ev_x(), top:200, width:160, height:50};
  function ev_x(){ return 200; }
  pop.style.left = Math.min(rect.right+6, window.innerWidth-200)+'px';
  pop.style.top = rect.top+'px';
  setTimeout(function(){ document.addEventListener('click', A.dagCtxClose, {once:true}); }, 0);
};
A.dagCtxClose = function(){ var m = document.getElementById('dagCtxMenu'); if(m) m.remove(); };
A._dagApiOf = function(id){
  return {update:function(nid, patch){ VC.updateNode(A._wfVc, nid, patch); }};
};
A.dagNodeCopy = function(id){
  var d0 = VC.getData(A._wfVc);
  var n = d0.nodes.find(function(x){return x.id===id;}); if(!n) return;
  var nid = 'cp_'+id+'_'+Date.now()%1000;
  VC.addNode(A._wfVc, Object.assign({}, JSON.parse(JSON.stringify(n)), {id:nid, name:n.name+'_copy', x:n.x+30, y:n.y+40}));
  UI.toast('节点已复制：'+n.name+'_copy', 'success');
};
A.dagRunNode = function(id){
  var d0 = VC.getData(A._wfVc);
  var n = d0.nodes.find(function(x){return x.id===id;});
  VC.updateNode(A._wfVc, id, {status:'running'});
  setTimeout(function(){ VC.updateNode(A._wfVc, id, {status:'success'}); UI.toast('节点「'+(n?n.name:id)+'」执行成功（当前节点执行）', 'success'); }, 800);
};
A.dagRunAfter = function(id){
  UI.toast('已从「'+id+'」向后执行（下游节点按依赖顺序入队）', 'info');
  A.dagDryRun();
};
A.dagNodeDel = function(id){
  VC.delNode(A._wfVc, id);
  UI.toast('已删除节点', 'info');
  setTimeout(function(){ A.dagCanvasChange(); }, 50);
};

/* 定时管理（cron 五段 + 触发时间预览 + 定时上线/下线） */
A.dagTiming = function(){
  var d = A._dagCur;
  var seg = (d.cron||'0 0 2 * * ?').split(/\s+/);
  UI.modal({title:'定时管理 - '+d.name, w:'w-md', footer:
    '<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn" onclick="A.dagTimingSave()">确定</button>'
    +(d.timingOn? '<button class="btn btn-danger" onclick="A._dagTimingToggle(0)">定时下线</button>':'<button class="btn btn-success" onclick="A._dagTimingToggle(1)">定时上线</button>'), body:
    '<div class="banner banner-info" style="margin-bottom:10px"><span class="b-ico">⏱</span><span>定时状态：<b>'+(d.timingOn? '已上线（调度中）':'未启用')+'</b> · 五段式 Cron（Quartz：秒可选，原型为 分 时 日 月 周）</span></div>'
    + '<div class="form-grid" style="grid-template-columns:repeat(5,1fr)">'
    + UI.fInput('分', 'cron_m', {value:seg[0]||'0'})
    + UI.fInput('时', 'cron_h', {value:seg[1]||'2'})
    + UI.fInput('日', 'cron_d', {value:seg[2]||'*'})
    + UI.fInput('月', 'cron_mo', {value:seg[3]||'*'})
    + UI.fInput('周', 'cron_w', {value:seg[4]||'?'})
    + '</div>'
    + '<div class="f-label" style="margin-top:8px">近 5 次触发时间预览</div>'
    + '<div class="table-wrap"><table class="tbl"><tbody>'
    + ['2026-09-13 02:00:00','2026-09-14 02:00:00','2026-09-15 02:00:00','2026-09-16 02:00:00','2026-09-17 02:00:00']
      .map(function(t){ return '<tr><td class="mono">'+t+'</td></tr>'; }).join('')
    + '</tbody></table></div>'
    + '<div class="f-help" style="margin-top:8px">失败告警组与超时策略在「保存」弹窗中配置；定时上线后按 Cron 生成每日实例。</div>'});
};
A.dagTimingSave = function(){
  var d = A._dagCur;
  d.cron = [UI.val('cron_m')||'0', UI.val('cron_h')||'2', UI.val('cron_d')||'*', UI.val('cron_mo')||'*', UI.val('cron_w')||'?'].join(' ');
  var el2 = document.getElementById('dagCronTxt'); if(el2) el2.textContent = d.cron;
  UI.closeModal(); UI.toast('定时配置已保存：'+d.cron, 'success');
};
A._dagTimingToggle = function(on){
  var d = A._dagCur;
  d.timingOn = !!on;
  UI.closeModal();
  UI.toast(on? '定时已上线：按 '+d.cron+' 调度生效':'定时已下线：停止生成新实例（历史实例不受影响）', on? 'success':'info');
};

/* 版本管理（DS：版本列表 + 切换到该版本） */
A.dagVersions = function(){
  var d = A._dagCur;
  if(!d.versions) d.versions = [
    {v:3, time:now+' 22:40', user:d.owner, note:'编排调整：增加依赖等待节点', cur:true},
    {v:2, time:yesterday+' 23:10', user:d.owner, note:'SQL 节点补充分区过滤参数'},
    {v:1, time:'2026-09-10 20:05', user:d.owner, note:'初始编排（开始 → 3 任务 → 结束）'}];
  UI.drawer({title:'版本管理 - '+d.name, w:'w-md', footer:false, body:
    '<div class="f-help" style="margin-bottom:8px">版本快照在「发布上线」与「保存」时自动生成；切换版本仅回滚编排定义，不影响已生成实例。</div>'
    + UI.tbl({id:'t_wfver', rowKey:'v', pageSize:6, data:function(){ return d.versions; },
      cols:[
        {t:'版本', k:'v', render:function(r){ return '<b>V'+r.v+'</b>'+(r.cur? ' '+tag('当前版本','blue'):''); }},
        {t:'提交时间', k:'time'},{t:'提交人', k:'user'},{t:'备注', k:'note'}
      ],
      ops:function(r){ return r.cur? '<span style="color:var(--text-3);font-size:11px">—</span>'
        : '<a onclick="A.dagVerSwitch('+r.v+')">切换到该版本</a><a onclick="UI.toast(\'版本对比：V'+r.v+' → 当前 V3（节点增删/连线差异，原型演示）\',\'info\')">对比</a>'; }})});
};
A.dagVerSwitch = function(v){
  UI.confirm({title:'切换版本', msg:'确定切换到 V'+v+' 吗?', detail:'切换后画布将回滚到该版本编排；当前未保存的编排调整将丢失。', onOk:function(){
    UI.toast('已切换到 V'+v+'（画布已回滚，重新发布后生效）', 'success'); UI.closeDrawer();
  }});
};

/* 保存弹窗（DS：基本信息 + 执行策略 + 全局参数 + 是否上线） */
A.dagSaveDlg = function(){
  var d = A._dagCur;
  UI.modal({title:'保存工作流定义', w:'w-lg', footer:'<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="A.dagSaveApply()">确定</button>', body:
    '<div class="f-label" style="margin-bottom:8px">基本信息</div>'
    + '<div class="form-grid">'
    + UI.fInput('工作流名称', 'swf_name', {value:d.name, req:true})
    + UI.fTextarea('描述', 'swf_desc', {value:d.desc||'', rows:2, full:true})
    + UI.fSelect('租户', 'swf_tenant', [{v:'default',t:'default（默认租户）'},{v:'etl',t:'etl'}], {value:d.tenant||'default'})
    + UI.fSelect('Worker分组', 'swf_group', [{v:'default',t:'default'},{v:'etl-group',t:'etl-group（批处理）'},{v:'rt-group',t:'rt-group（实时）'}], {value:d.workerGroup||'default'})
    + UI.fSelect('告警组', 'swf_alarm', [{v:'g0',t:'（不发送）'},{v:'g-data',t:'数据平台值班组'}], {value:d.alarmGroup||'g-data'})
    + UI.fInput('超时告警（分）', 'swf_timeout', {value:d.timeout||'120', type:'number'})
    + UI.fSelect('执行策略', 'swf_exec', [
        {v:'parallel',t:'并行'},{v:'serial_wait',t:'串行等待'},{v:'serial_discard',t:'串行抛弃'},{v:'serial_priority',t:'串行优先'},{v:'recover_serial_wait',t:'串行恢复'}], {value:d.execStrategy||'parallel', full:true})
    + '</div>'
    + '<div class="f-label" style="margin:10px 0 6px">全局参数（KEY / VALUE）</div>'
    + '<div class="table-wrap"><table class="tbl"><thead><tr><th>键</th><th>值</th><th>说明</th></tr></thead><tbody>'
    + '<tr><td class="mono">biz_date</td><td class="mono">$[yyyy-MM-dd-1]</td><td style="color:var(--text-3)">业务日期（T-1）</td></tr>'
    + '<tr><td class="mono">src_db</td><td class="mono">greatdb_gdb</td><td style="color:var(--text-3)">上游业务库</td></tr>'
    + '</tbody></table></div>'
    + '<div style="margin-top:10px">'+UI.fSwitch('同时更新工作流定义（保存后保持当前上线状态）', 'swf_online', d.status==='online')+'</div>'
    + '<div class="lock-tip" style="margin-top:8px">保存动作：① 写回编排画布（节点/连线）② 生成版本快照 V'+((d.versions? d.versions.length:3)+1)+' ③ 按执行策略更新调度配置。</div>'});
};
A.dagSaveApply = function(){
  var d = A._dagCur;
  var name = UI.val('swf_name');
  if(!name){ UI.toast('DAG图名称不能为空', 'warn'); return false; }
  d.name = name; d.desc = UI.val('swf_desc'); d.tenant = UI.val('swf_tenant');
  d.workerGroup = UI.val('swf_group'); d.alarmGroup = UI.val('swf_alarm');
  d.timeout = UI.val('swf_timeout')||'120'; d.execStrategy = UI.val('swf_exec');
  A.dagSave(true);
  d.versions = d.versions||[{v:3,time:now+' 22:40',user:d.owner,note:'当前版本',cur:true}];
  d.versions.forEach(function(x){ x.cur=false; });
  d.versions.unshift({v:d.versions.length+1, time:now+' '+new Date().toTimeString().slice(0,8), user:d.owner, note:'保存生成版本快照', cur:true});
  var nm = document.getElementById('dagWfName'); if(nm) nm.textContent = d.name;
  UI.closeModal();
  UI.toast('工作流定义已保存：节点 '+d.nodesDetail.length+' 个 · 版本 V'+d.versions[0].v+' · 执行策略 '+d.execStrategy, 'success');
  AI.show('保存完成 ✦\n· 编排画布已写回（节点 '+d.nodesDetail.length+' 个，含开始/结束）\n· 版本快照 V'+d.versions[0].v+' 已生成，可随时回滚\n· 全局参数 ${biz_date} 等已随定义生效\n· 建议：发布前执行「✓ 校验」与「▶ 试运行」完成自检。');
};

/* 画布变化：为分支线补 label（成功/失败、分支N）+ 静默刷新校验面板 */
A.dagCanvasChange = function(){
  if(!A._wfVc) return;
  var d = VC.getData(A._wfVc);
  var changed = false, cnt = {};
  d.edges.forEach(function(e){
    if(e.kind==='branch' && !e.label){
      var from = d.nodes.find(function(n){return n.id===e.from;});
      var key = from? from.id : '_';
      cnt[key] = (cnt[key]||0)+1;
      e.label = (from && from.type==='case')? '分支'+cnt[key] : (cnt[key]===1? '成功':'失败');
      changed = true;
    }
  });
  if(changed) VC.setData(A._wfVc, d);
  A.dagValidate(true);
};

/* 节点抽屉配置：①基础 ②任务内容 ③验证与业务逻辑 */
A.dagNodeEdit = function(n, api){
  var isSys = n.type==='start'||n.type==='end';
  var c = n.cfg||{};
  var self = A._dagCur;
  UI.drawer({title:'节点配置 - '+n.name+'（'+(A.dagTypeName[n.type]||'系统节点')+'）', w:'w-lg', body:
    '<div class="tabs" id="wfNtTabs"><span class="tab on" onclick="A._wfnTab(this,0)">① 基础</span><span class="tab" onclick="A._wfnTab(this,1)">② 任务内容</span><span class="tab" onclick="A._wfnTab(this,2)">③ 验证与业务逻辑</span></div>'
    + '<div id="wfn0"><div class="form-grid">'
    + UI.fInput('节点名称', 'dn_name', {value:n.name, req:true})
    + UI.fInput('任务超时（秒）', 'dn_timeout', {value:c['超时']||'600', type:'number'})
    + UI.fInput('重试次数', 'dn_retry', {value:c['重试次数']||'0', type:'number'})
    + UI.fInput('重试间隔（秒）', 'dn_interval', {value:c['重试间隔']||'60', type:'number'})
    + UI.fSelect('失败策略', 'dn_fail', [{v:'阻塞下游',t:'阻塞下游（重试耗尽后告警，下游等待）'},{v:'失败继续',t:'失败继续（下游照常执行）'},{v:'跳过',t:'跳过该节点（标记警告）'}], {value:c['失败策略']||'阻塞下游'})
    + '</div></div>'
    + '<div id="wfn1" style="display:none">'+ A.dagNodeContent(n, self) +'</div>'
    + '<div id="wfn2" style="display:none">'
    + '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>验证规则：①任务内容非空且引用对象有效 ②上游依赖/等待策略明确 ③业务口径与指标定义一致。</span></div>'
    + UI.fTextarea('业务逻辑说明', 'dn_logic', {value:c['业务逻辑']||'', rows:3, ph:'描述该节点的业务口径、注意事项（AI 审查将引用）'})
    + '<div style="margin-top:6px"><button class="btn btn-sm" onclick="UI.toast(\'节点验证通过：配置完整，引用对象有效 ✓\',\'success\')">▶ 验证此节点</button>'
    + '<button class="btn btn-sm" style="margin-left:6px" onclick="AI.show(\''+A.dagAiMsg(n, isSys)+'\')">✦ AI 审查</button></div>'
    + '</div>',
    onOk:function(){
      var name = UI.val('dn_name');
      if(!name){ UI.toast('请填写节点名称', 'warn'); return false; }
      var cfg = Object.assign({}, n.cfg, {'超时':UI.val('dn_timeout')||'600', '重试次数':UI.val('dn_retry')||'0',
        '重试间隔':UI.val('dn_interval')||'60', '失败策略':UI.val('dn_fail')||'阻塞下游', '业务逻辑':UI.val('dn_logic')});
      if(!isSys){
        if(n.type==='sql'||n.type==='proc'){ cfg['SQL']=UI.val('dn_sql'); if(n.type==='sql') cfg['产出表']=UI.val('dn_out'); }
        else if(n.type==='sync'||n.type==='etl'||n.type==='script'||n.type==='subwf'){ cfg['引用']=UI.val('dn_ref'); if(n.type==='script') cfg['参数']=UI.val('dn_args'); }
        else if(n.type==='depwait'){ cfg['依赖工作流']=UI.val('dn_ref'); cfg['依赖表']=UI.val('dn_table'); cfg['周期']=UI.val('dn_period'); cfg['策略']=UI.val('dn_strategy'); }
        else if(n.type==='if'||n.type==='case'){ cfg['条件']=UI.val('dn_cond'); }
      }
      api.update(n.id, {name:name, cfg:cfg, summary:A.dagSummary(n, cfg, isSys)});
      UI.toast('节点配置已保存，摘要已更新（画布悬浮可见）', 'success');
    }});
};
A._wfnTab = function(el, i){
  document.querySelectorAll('#wfNtTabs .tab').forEach(function(t, idx){ t.classList.toggle('on', idx===i); });
  [0,1,2].forEach(function(x){ var dd = document.getElementById('wfn'+x); if(dd) dd.style.display = x===i? '':'none'; });
};
A.dagNodeContent = function(n, self){
  var c = n.cfg||{};
  var help = '<div class="f-help">支持内置参数 ${biz_date}（业务日期）等，见「参数管理 M12」。</div>';
  if(n.type==='start'||n.type==='end') return '<div class="empty" style="padding:26px"><span class="e-ico">▣</span><p>系统固定节点，无需任务内容</p></div>';
  if(n.type==='sql') return '<div class="form-grid">'
    + UI.fSelect('产出表', 'dn_out', DB.metaTables.map(function(t){return {v:t.name,t:t.name};}).concat([{v:'-',t:'（无产出）'}]), {value:c['产出表']||'-'})
    + UI.fTextarea('SQL 内容', 'dn_sql', {value:c['SQL']||"INSERT OVERWRITE TABLE dws_pay_summary_daily PARTITION (dt='${biz_date}')\nSELECT ...", rows:7, mono:true, full:true})
    + '</div>'+help;
  if(n.type==='proc') return '<div class="form-grid">'
    + UI.fTextarea('过程调用（CALL）', 'dn_sql', {value:c['SQL']||"CALL dws_refresh_summary('${biz_date}');", rows:3, mono:true, full:true})
    + '</div><div class="f-help">调用目标库存储过程，参数支持内置变量传递。</div>';
  if(n.type==='sync') return '<div class="form-grid">'
    + UI.fSelect('引用同步任务（M05 批处理）', 'dn_ref', DB.syncBatches.map(function(b){return {v:b.id, t:b.id+'（'+b.srcName+' → '+b.target+'）'};}), {value:c['引用']||(DB.syncBatches[0]||{}).id, full:true})
    + '</div><div class="f-help">引用批量同步任务作为节点，调度时触发同步并等待完成。</div>';
  if(n.type==='etl'){
    var pubs = DB.etlTasks.filter(function(t){return t.status==='published';});
    return '<div class="form-grid">'
      + UI.fSelect('引用 ETL 任务（仅已发布）', 'dn_ref', pubs.map(function(t){return {v:t.id, t:t.name+'（'+t.type+' · '+t.id+'）'};}), {value:c['引用']||(pubs[0]||{}).id, full:true})
      + '</div><div class="f-help">仅可选择已发布（published）的 ETL 任务；草稿任务请先到「ETL 任务」发布。</div>';
  }
  if(n.type==='script'){
    var sp = DB.scripts.filter(function(t){return t.status==='published';});
    return '<div class="form-grid">'
      + UI.fSelect('引用脚本（M14 脚本库）', 'dn_ref', sp.map(function(t){return {v:t.id, t:t.name+'（'+t.lang+' · '+t.id+'）'};}), {value:c['引用']||(sp[0]||{}).id, full:true})
      + UI.fInput('脚本参数', 'dn_args', {value:c['参数']||'${src_table} ${biz_date}', full:true})
      + '</div><div class="f-help">远程执行走执行节点（M14），参数以空格分隔传入 argv。</div>';
  }
  if(n.type==='depwait') return '<div class="form-grid">'
    + UI.fSelect('上游工作流', 'dn_ref', DB.workflows.filter(function(w){return w.id!==(self&&self.id);}).map(function(w){return {v:w.name, t:w.name+'（'+w.id+' · '+(w.status==='online'?'已上线':'草稿/下线')+'）'};}), {value:c['依赖工作流']||(DB.workflows[0]||{}).name, full:true})
    + UI.fSelect('依赖表（上游产出）', 'dn_table', DB.metaTables.map(function(t){return {v:t.name,t:t.name};}), {value:c['依赖表']||'ads_kpi_report'})
    + UI.fSelect('周期对齐', 'dn_period', [{v:'T-1',t:'T-1（昨日分区）'},{v:'T',t:'T（今日实时）'}], {value:c['周期']||'T-1'})
    + UI.fSelect('等待策略', 'dn_strategy', [{v:'等待完成',t:'等待上游工作流完成'},{v:'校验行数',t:'校验分区行数>0'}], {value:c['策略']||'等待完成'})
    + '</div><div class="f-help">从该节点连线到下游任务时建议使用依赖线（dep）；也可在「依赖管理」维护表级依赖。</div>';
  if(n.type==='if') return '<div class="form-grid">'
    + UI.fTextarea('判定条件', 'dn_cond', {value:c['条件']||'${p_row_cnt} > 0', rows:2, mono:true, full:true})
    + '</div><div class="f-help">从该节点拉「分支线」到下游：第1条分支线 label=成功（走主链路），第2条 label=失败（触发告警）。</div>';
  if(n.type==='case') return '<div class="form-grid">'
    + UI.fTextarea('分支条件（一行一路）', 'dn_cond', {value:c['条件']||"channel = 'ALIPAY'\nchannel = 'WECHAT'\n其他", rows:3, mono:true, full:true})
    + '</div><div class="f-help">每条分支线自动标注 分支1/分支2/…，与条件行顺序对应。</div>';
  if(n.type==='subwf') return '<div class="form-grid">'
    + UI.fSelect('子工作流', 'dn_ref', DB.workflows.filter(function(w){return w.id!==(self&&self.id);}).map(function(w){return {v:w.name, t:w.name+'（'+w.id+'）'};}), {value:c['引用']||(DB.workflows[0]||{}).name, full:true})
    + '</div><div class="f-help">子工作流需已上线（online）方可被调度；父流程等待其完成后继续。</div>';
  return '';
};
A.dagSummary = function(n, cfg, isSys){
  if(isSys) return n.type==='start'? '工作流入口（固定节点）' : '工作流出口（固定节点）';
  var t = A.dagTypeName[n.type]||n.type;
  if(n.type==='sql'||n.type==='proc') return t+' · '+String(cfg['SQL']||'（待配置）').replace(/\s+/g,' ').slice(0,40);
  if(n.type==='depwait') return t+' · 依赖 '+(cfg['依赖工作流']||'-')+' · '+(cfg['依赖表']||'-')+'（'+(cfg['周期']||'T-1')+' '+(cfg['策略']||'')+'）';
  if(n.type==='if'||n.type==='case') return t+' · '+String(cfg['条件']||'（待配置）').replace(/\s+/g,' ').slice(0,40);
  if(n.type==='subwf') return t+' · 子流程 '+(cfg['引用']||'-');
  if(n.type==='script') return t+' · '+(cfg['引用']||'-')+' · 参数 '+String(cfg['参数']||'-').slice(0,20);
  return t+' · 引用 '+(cfg['引用']||'-');
};
A.dagAiMsg = function(n, isSys){
  var c = n.cfg||{};
  var rows = ['节点「'+n.name+'」（'+(A.dagTypeName[n.type]||'系统节点')+'）AI 审查结果：'];
  if(isSys) rows.push('· 系统固定节点，仅作为流程出入口 ✓\n· 检查入口/出口收敛性：通过 ✓');
  else if(n.type==='sql'||n.type==='proc') rows.push('· SQL 语法检查通过 ✓\n· 建议：WHERE 条件补充分区过滤 dt=${biz_date}\n· 产出表口径与上游模型定义对齐 ✓');
  else if(n.type==='depwait') rows.push('· 依赖工作流 '+(c['依赖工作流']||'-')+' 产出周期 '+(c['周期']||'T-1')+' ✓\n· 建议：等待策略用「校验分区行数>0」防止空跑\n· 依赖关系无环 ✓');
  else if(n.type==='if'||n.type==='case') rows.push('· 条件表达式解析通过 ✓\n· 建议：CASE 补充默认兜底分支\n· 分支线 label 已自动标注 成功/失败');
  else if(n.type==='subwf') rows.push('· 子工作流已上线，可被调度 ✓\n· 建议：本节点超时 ≤ 子流程 SLA 时限\n· 参数透传 ${biz_date} ✓');
  else rows.push('· 引用对象有效 ✓\n· 任务内容完整 ✓\n· 建议：失败策略与重试配置符合 SLA 要求');
  rows.push('· 综合评分 92/100 · 无阻塞问题');
  return rows.join('\n').replace(/'/g,'');
};

/* 校验面板：渲染 VC.validate 结果（成功/警告横幅） */
A.dagValidate = function(quiet){
  if(!A._wfVc) return;
  var errs = VC.validate(A._wfVc);
  var box = document.getElementById('wfValidateBox'); if(!box) return;
  box.innerHTML = errs.length? errs.map(function(e){
    return '<div class="banner '+(e.level==='error'?'banner-danger':'banner-warn')+'" style="margin-bottom:6px;padding:8px 11px"><span class="b-ico">'+(e.level==='error'?'✗':'⚠')+'</span><span style="font-size:12px">'+UI.esc(e.msg)+'</span></div>';
  }).join('') : '<div class="banner banner-success" style="padding:8px 11px"><span class="b-ico">✓</span><span style="font-size:12px">校验通过：无孤立节点、无环路，流程从开始收敛到结束</span></div>';
  if(!quiet) UI.toast(errs.filter(function(e){return e.level==='error';}).length? '校验发现 '+errs.length+' 个问题':'工作流校验通过', errs.length? 'warn':'success');
};

/* 试运行：拓扑序逐节点点亮 + 日志逐行输出 */
A.dagRunMsg = function(n){
  var m = {start:'调度启动 · 业务日期 ${biz_date}=2026-09-11', end:'工作流收敛完成',
    sync:'同步完成 · 125万行 · 80s', sql:'SQL 执行成功 · 影响 1860 行 · 40s', etl:'ETL 执行成功 · 398万行 · 95s',
    script:'脚本退出码 0 · 12s', proc:'过程调用成功 · 3s', depwait:'上游分区 dt=2026-09-11 就绪 ✓ · 2s',
    if:'条件成立 → 成功分支', case:'命中分支1', subwf:'子工作流运行成功 · 3m'};
  return m[n.type]||'完成 · 30s';
};
A.dagDryRun = function(){
  if(!A._wfVc){ UI.toast('编辑器未就绪', 'warn'); return; }
  A.dagValidate(true);
  var d = VC.getData(A._wfVc);
  var log = document.getElementById('wfRunLog'); if(!log) return;
  log.innerHTML = '<span class="lg-info">ℹ 试运行（预演，不产生实例）· '+new Date().toLocaleTimeString()+'</span>';
  var order = [];
  (function(){
    var indeg = {}, out = {};
    d.nodes.forEach(function(n){ indeg[n.id]=0; out[n.id]=[]; });
    d.edges.forEach(function(e){ if(out[e.from]&&indeg[e.to]!=null){ out[e.from].push(e.to); indeg[e.to]++; }});
    var q = d.nodes.filter(function(n){return !indeg[n.id];}).map(function(n){return n.id;});
    while(q.length){ var cur=q.shift(); order.push(cur); out[cur].forEach(function(t){ if(--indeg[t]===0) q.push(t); }); }
  })();
  order.forEach(function(id, i){
    setTimeout(function(){
      var n = d.nodes.find(function(x){return x.id===id;});
      if(n){ n.status='success'; VC.updateNode(A._wfVc, id, {status:'success'}); }
      d.edges.forEach(function(e){ if(e.from===id) e.run = true; });
      log.insertAdjacentHTML('beforeend', '<br><span class="lg-ok">✓ ['+String(i+1).padStart(2,'0')+'] '+UI.esc(n?n.name:id)+' '+A.dagRunMsg(n||{})+'</span>');
      log.scrollTop = log.scrollHeight;
    }, 380*(i+1));
  });
  setTimeout(function(){
    log.insertAdjacentHTML('beforeend', '<br><span class="lg-ok">✔ 试运行完成：'+d.nodes.length+' 节点全部成功 · 依赖线就绪校验通过 · 可发布上线</span>');
    log.scrollTop = log.scrollHeight;
    VC.setData(A._wfVc, d);
  }, 380*(order.length+1));
};

/* 保存：写回工作流定义（flow 全量 + nodesDetail 兼容既有页面） */
A.dagSave = function(silent){
  var d = A._dagCur;
  if(!d || !A._wfVc) return;
  var data = VC.getData(A._wfVc);
  d.flow = data;
  d.nodesDetail = data.nodes.filter(function(n){return n.type!=='start'&&n.type!=='end';}).map(function(n){
    var dep = data.edges.filter(function(e){return e.to===n.id && e.from!=='start';}).map(function(e){return e.from;});
    var c = n.cfg||{};
    return {id:n.id, name:n.name, type:A.dagTypeName[n.type]||n.type, dep:dep,
      outTable:(n.type==='depwait')? (c['依赖表']||'-') : ((c['产出表'] && c['产出表']!=='-')? c['产出表'] : (c['引用']||'-')),
      retry:parseInt(c['重试次数'],10)||0, dur:c['耗时']||'-'};
  });
  d.nodes = d.nodesDetail.length;
  if(!silent) UI.toast('工作流定义已保存：任务节点 '+d.nodesDetail.length+' 个（画布含开始/结束）', 'success');
};

/* 发布上线（先保存再校验节点数） */
A.dagPublish = function(){
  var d = A._dagCur; if(!d) return;
  A.dagSave(true);
  if(!d.nodesDetail.length){ UI.toast('请先从元件库拖入任务节点并连线', 'warn'); return; }
  UI.confirm({title:'发布上线', msg:'确认发布工作流「'+d.name+'」？', detail:'上线后按 Cron（'+d.cron+'）自动调度；发布进行版本快照 v1，支持回滚。', onOk:function(){
    d.status = 'online'; UI.toast('工作流已上线，调度生效', 'success'); App.resolve();
  }});
};
})();
