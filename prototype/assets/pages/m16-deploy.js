/* ============================================================
   M16 一键部署（部署中心/集群监控/组件日志/告警管理/运维操作）
   闭环：部署向导(6步) → 集群监控 → 告警产生 → 运维处置 → 恢复
   ============================================================ */
(function(){
/* ---- 部署中心 ---- */
App.reg('#/dep/center', '部署中心', function(){
  var html = UI.pageHead('一键部署中心',
    '信创环境（麒麟V10/鲲鹏920/万里数据库）一键部署：套件编排 → 前置检查 → 安装执行 → 健康检查；支持备份与回滚',
    '<button class="btn btn-primary" onclick="App.go(\'#/dep/wizard\')">⚙ 一键部署向导</button>');
  html += '<div class="grid grid-4" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#475569">⛅</span><div><div class="stat-num">'+DB.servers.filter(function(s){return s.status==='online';}).length+'/'+DB.servers.length+'</div><div class="stat-label">节点在线</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+DB.components.filter(function(c){return c.status==='running';}).length+'</div><div class="stat-label">组件运行中</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#1668dc">📋</span><div><div class="stat-num">'+DB.suites.filter(function(s){return s.status==='deployed';}).length+'/'+DB.suites.length+'</div><div class="stat-label">套件已部署</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#d97706">⇩</span><div><div class="stat-num">'+DB.backups.length+'</div><div class="stat-label">备份任务（全部成功）</div></div></div></div>';
  html += UI.card('部署套件', '<div class="grid" style="grid-template-columns:repeat(2,1fr)">'
    + DB.suites.map(function(s){
      var dep = s.status==='deployed';
      return '<div class="stat-card" style="align-items:flex-start"><span class="type-icon" style="background:'+(dep?'#16a34a':'#8c94a6')+'">'+(dep?'✓':'⊕')+'</span>'
        +'<div style="flex:1"><b>'+s.name+'</b><div style="font-size:11.5px;color:var(--text-3);margin:4px 0">'+s.comps+' · '+UI.esc(s.desc)+'</div>'
        +'<div style="display:flex;gap:6px;align-items:center">'+(dep? tag('已部署','green') : tag('未部署','gray'))
        +'<button class="btn btn-sm" onclick="'+(dep?'UI.toast(\'套件已部署，可在集群监控中查看组件健康\',\'info\')':'App.go(\'#/dep/wizard\')')+'">'+(dep?'查看':'部署')+'</button></div></div></div>';
    }).join('')+'</div>');
  /* 部署拓扑预览：组件 → 节点分布矩阵，点击节点跳转运行拓扑视图定位 */
  html += UI.card('部署拓扑预览', '<div style="font-size:11.5px;color:var(--text-3);margin-bottom:10px">已部署组件在集群节点上的分布全景；点击节点卡可跳转集群运行拓扑视图定位。</div>'
    +'<div class="grid" style="grid-template-columns:repeat(2,1fr)">'
    + DB.components.filter(function(c){return c.status==='running';}).map(function(c){
      return '<div style="border:1px solid var(--border);border-radius:9px;padding:11px 12px;background:#fff">'
        +'<div style="display:flex;align-items:center;gap:8px;margin-bottom:9px"><span class="type-icon" style="background:#0891b2;width:26px;height:26px;font-size:11px">'+UI.esc(c.name.slice(0,2).toUpperCase())+'</span>'
        +'<div style="flex:1"><b style="font-size:12.5px">'+c.name+'</b><span style="font-size:11px;color:var(--text-3)"> v'+c.version+' · '+UI.esc(c.role)+'</span></div>'
        +(c.health==='健康'? tag('健康','green') : tag(c.health,'orange'))+'</div>'
        +'<div>'+c.nodes.map(function(n){
          return '<span class="mono" onclick="A.topoLocate(\''+n.split('(')[0]+'\')" style="display:inline-block;padding:3px 9px;margin:0 6px 6px 0;border:1px solid var(--border);border-radius:6px;font-size:11px;background:#f8fafc;cursor:pointer">'+n+'</span>';
        }).join('')+'</div></div>';
    }).join('')+'</div>');
  html += UI.card('组件清单', UI.tbl({
    id:'t_cp', rowKey:'id', pageSize:8, searchKeys:['id','name','role'], searchPh:'搜索组件',
    filters:[{k:'status', label:'状态', options:[{v:'running',t:'运行中'},{v:'undeploy',t:'未部署'}]}],
    data:function(){ return DB.components; },
    cols:[
      {t:'组件', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+(r.version!=='-'?'v'+r.version:'未安装')+'</div>';}},
      {t:'角色', k:'role'},
      {t:'节点', render:function(r){return r.nodes.length? r.nodes.join('，'):'-';}},
      {t:'CPU/内存', render:function(r){return r.status==='running'? r.cpu+'% / '+r.mem+'%':'-';}},
      {t:'健康', render:function(r){return r.status==='running'? st('success'):st(r.status==='undeploy'?'disabled':'failed');}},
      {t:'运行天数', k:'upDays', render:function(r){return r.upDays? r.upDays+' 天':'-';}}
    ],
    ops:function(r){
      if(r.status==='undeploy') return '<a onclick="App.go(\'#/dep/wizard\')">部署</a>';
      return '<a onclick="App.go(\'#/dep/monitor\')">监控</a><a onclick="UI.toast(\'配置管理：修改 '+r.name+' 参数（原型演示）\',\'info\')">配置</a><a class="danger" onclick="A.cpRestart(\''+r.id+'\')">重启</a>';
    }}));
  html += UI.card('备份管理', UI.tbl({
    id:'t_bk', rowKey:'id', pageSize:5, searchKeys:['id','target'], data:function(){ return DB.backups; },
    cols:[{t:'备份对象', k:'target'},{t:'时间', k:'time'},{t:'大小', k:'size'},{t:'方式', k:'type'},{t:'结果', render:function(r){return st(r.status);}}],
    ops:function(r){ return '<a onclick="UI.toast(\'备份下载：'+r.target+'（'+r.size+'）已开始\',\'success\')">下载</a>'; }}),
    '<button class="btn" onclick="A.bkNow()">立即备份</button><button class="btn" onclick="UI.toast(\'备份策略：每日 03:00 全量，保留 30 天\',\'info\')">备份策略</button>');
  return html;
});
A.bkNow = function(){
  UI.toast('正在执行手动备份（平台配置库）...', 'info');
  setTimeout(function(){
    DB.backups.unshift({id:'BK0'+(DB.backups.length+1), target:'平台配置库（手动）', time:now+' 23:35', size:'860MB', type:'手动', status:'success'});
    UI.toast('备份完成：860MB 已存至 /backup/'+now, 'success'); App.resolve();
  }, 1200);
};
A.cpRestart = function(id){
  var c = DB.components.find(function(x){return x.id===id;});
  UI.confirm({title:'重启组件', danger:true, msg:'确认重启 '+c.name+'？', detail:'重启期间依赖该组件的任务可能短暂失败，建议在业务低峰执行。', onOk:function(){
    UI.toast('正在滚动重启 '+c.name+' ...', 'info');
    setTimeout(function(){ UI.toast(c.name+' 重启完成，健康检查通过', 'success'); }, 1500);
  }});
};
A.topoLocate = function(ip){
  var sv = DB.servers.find(function(x){return x.ip===ip;});
  var d = A._topoData;
  var ids = d? Object.keys(d.map).filter(function(k){
    var n = d.map[k];
    if(!n.cp) return false;
    var c = DB.components.find(function(x){return x.id===n.cp;});
    return c && c.nodes.join(',').indexOf(ip)>=0;
  }) : [];
  A._topoPending = ids;
  UI.toast('已定位 '+(sv? sv.name : ip)+'（'+ip+'），正在打开集群运行拓扑...', 'info');
  App.go('#/dep/monitor');
};

/* ---- 部署向导（6步） ---- */
App.reg('#/dep/wizard', '部署向导', function(){
  var html = UI.pageHead('一键部署向导', '选择组件 → 选择节点 → 填写配置 → 前置检查 → 安装执行 → 健康检查');
  html += '<div class="card no-head"><div class="card-body" id="depWizBody">'+A._depStep(0)+'</div></div>';
  return html;
});
A._depData = {step:0, comp:null, nodes:[]};
A._depStep = function(s){
  A._depData.step = s;
  var steps = ['选择组件','选择节点','填写配置','前置检查','安装执行','健康检查'];
  var inner = '';
  if(s===0){
    inner = DB.components.filter(function(c){return c.status==='undeploy';}).map(function(c){
      return '<div class="stat-card hoverable" style="'+(A._depData.comp===c.id?'border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light)':'')+'" onclick="A._depPick(\''+c.id+'\')">'
        +'<span class="type-icon" style="background:#0891b2">'+UI.esc(c.name.slice(0,2).toUpperCase())+'</span>'
        +'<div><b style="font-size:13px">'+c.name+'</b><div style="font-size:11px;color:var(--text-3)">'+c.role+'（'+(c.version!=='-'?'v'+c.version:'待定版本')+'）</div></div></div>';
    }).join('');
    inner = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>以下为未部署组件；已部署组件可在集群监控中管理。</span></div><div class="grid" style="grid-template-columns:repeat(2,1fr)">'+inner+'</div>'
      + '<div style="margin-top:16px;display:flex;justify-content:flex-end"><button class="btn btn-primary" onclick="A._depNext()">下一步 →</button></div>';
  }
  if(s===1){
    inner = DB.servers.map(function(sv){
      var on = A._depData.nodes.indexOf(sv.id)>=0;
      return '<label style="display:flex;gap:9px;align-items:center;padding:10px 12px;border:1px solid '+(on?'var(--primary)':'var(--border)')+';border-radius:8px;margin-bottom:8px;cursor:pointer;background:'+(on?'var(--info-bg)':'#fff')+'"><input type="checkbox" '+(on?'checked':'')+' '+(sv.status!=='online'?'disabled':'')+' onchange="A._depNode(\''+sv.id+'\',this.checked)">'
        +'<div><b>'+sv.name+'</b>（'+sv.ip+'）<div style="font-size:11px;color:var(--text-3)">'+sv.cpu+'/'+sv.mem+'/'+sv.disk+' · '+sv.os+' · '+sv.role+'</div></div>'
        +'<span style="margin-left:auto">'+(sv.status==='online'? st('success'):st('offline'))+'</span></label>';
    }).join('')
    + '<div style="display:flex;justify-content:space-between;margin-top:14px"><button class="btn" onclick="A._depStepRender(0)">← 上一步</button><button class="btn btn-primary" onclick="A._depNext()">下一步 →</button></div>';
  }
  if(s===2){
    inner = '<div class="form-grid" style="max-width:720px">'
      + UI.fInput('安装目录', 'dw_dir', {value:'/opt/datara', req:true})
      + UI.fInput('数据目录', 'dw_data', {value:'/data/dep', req:true})
      + UI.fInput('JDK 路径', 'dw_jdk', {value:'/usr/lib/jdk1.8'})
      + UI.fInput('组件端口', 'dw_port', {value:'9092'})
      + UI.fSwitch('自动启动与开机自启', 'dw_auto', true)
      + UI.fSwitch('部署后自动执行健康检查', 'dw_health', true)
      + '</div><div class="lock-tip">配置将渲染为各组件 yaml/conf 并分发至所选节点；信创环境自动匹配 aarch64 二进制包。</div>'
      + '<div style="display:flex;justify-content:space-between;margin-top:14px"><button class="btn" onclick="A._depStepRender(1)">← 上一步</button><button class="btn btn-primary" onclick="A._depNext()">前置检查 →</button></div>';
  }
  if(s===3){
    inner = '<div id="precheckBox">'+DB.precheckItems.map(function(it, i){
      return '<div class="checker-line run" id="pc_'+i+'">◌ <b>'+it.item+'</b><span style="margin-left:auto">检查中...</span></div>';
    }).join('')+'</div>'
    + '<div style="display:flex;justify-content:space-between;margin-top:14px"><button class="btn" onclick="A._depStepRender(2)">← 上一步</button><button class="btn btn-primary" id="pcNextBtn" disabled onclick="A._depStepRender(4)">开始安装 →</button></div>';
  }
  if(s===4){
    var comp = DB.components.find(function(c){return c.id===A._depData.comp;});
    inner = '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>正在向 '+A._depData.nodes.length+' 个节点分发并安装 '+comp.name+'（滚动安装，节点逐台执行）...</span></div>'
      + '<div id="installBox">'+A._depData.nodes.map(function(nid, i){
        var sv = DB.servers.find(function(x){return x.id===nid;});
        return '<div class="checker-line run" id="in_'+i+'">◌ <b>'+sv.name+'（'+sv.ip+'）</b><span style="margin-left:auto">排队中...</span></div>';
      }).join('')+'</div>'
      + '<div style="display:flex;justify-content:flex-end;margin-top:14px"><button class="btn btn-primary" id="inNextBtn" style="display:none" onclick="A._depStepRender(5)">健康检查 →</button></div>';
  }
  if(s===5){
    inner = '<div class="banner banner-success"><span class="b-ico">✓</span><span>部署完成！组件已上线并纳入监控，健康检查全部通过。</span></div>'
      + '<div class="checker-line ok"><span>✓</span><b>服务端口监听</b><span style="margin-left:auto">正常</span></div>'
      + '<div class="checker-line ok"><span>✓</span><b>集群元数据注册</b><span style="margin-left:auto">正常</span></div>'
      + '<div class="checker-line ok"><span>✓</span><b>样例读写测试</b><span style="margin-left:auto">通过</span></div>'
      + '<div style="margin-top:14px;display:flex;gap:8px"><button class="btn btn-primary" onclick="A._depFinish()">完成并返回部署中心</button><button class="btn" onclick="App.go(\'#/dep/monitor\')">前往集群监控</button></div>';
  }
  return UI.steps(steps, s) + inner;
};
/* 步骤切换渲染：写入 DOM 后启动检查/安装动画 */
A._depStepRender = function(s){
  var el = document.getElementById('depWizBody'); if(!el) return;
  el.innerHTML = A._depStep(s);
  if(s===3){
    DB.precheckItems.forEach(function(it, i){
      setTimeout(function(){
        var e = document.getElementById('pc_'+i); if(!e) return;
        e.className='checker-line '+(it.result==='pass'?'ok':'err');
        e.innerHTML = '<span>'+(it.result==='pass'?'✓':'⚠')+'</span><b>'+it.item+'</b><span style="margin-left:auto">'+it.detail+'</span>';
        if(i===DB.precheckItems.length-1){ var b=document.getElementById('pcNextBtn'); if(b) b.disabled=false; }
      }, 550*(i+1));
    });
  }
  if(s===4){
    A._depData.nodes.forEach(function(nid, i){
      setTimeout(function(){
        var e = document.getElementById('in_'+i); if(!e) return;
        var sv = DB.servers.find(function(x){return x.id===nid;});
        e.className='checker-line ok';
        e.innerHTML = '<span>✓</span><b>'+sv.name+'（'+sv.ip+'）</b><span style="margin-left:auto">安装完成 · 服务启动成功</span>';
        if(i===A._depData.nodes.length-1){ var b=document.getElementById('inNextBtn'); if(b) b.style.display='inline-block'; }
      }, 800*(i+1));
    });
  }
};
A._depPick = function(id){ A._depData.comp = id; A._depStepRender(0); };
A._depNode = function(id, on){
  var i = A._depData.nodes.indexOf(id);
  if(on && i<0) A._depData.nodes.push(id);
  if(!on && i>=0) A._depData.nodes.splice(i,1);
};
A._depNext = function(){
  var s = A._depData.step;
  if(s===0){ if(!A._depData.comp){ UI.toast('请选择要部署的组件', 'warn'); return; } A._depStepRender(1); }
  else if(s===1){ if(!A._depData.nodes.length){ UI.toast('请至少选择 1 个在线节点', 'warn'); return; } A._depStepRender(2); }
  else if(s===2){ if(!UI.val('dw_dir')){ UI.toast('请填写安装目录', 'warn'); return; } A._depStepRender(3); }
};
A._depFinish = function(){
  var c = DB.components.find(function(x){return x.id===A._depData.comp;});
  c.status='running'; c.health='健康'; c.upDays=1; c.cpu=12+Math.floor(Math.random()*30); c.mem=25+Math.floor(Math.random()*30);
  c.nodes = A._depData.nodes.map(function(nid){ var sv=DB.servers.find(function(x){return x.id===nid;}); return sv.ip; });
  UI.toast(c.name+' 部署完成并已上线', 'success');
  App.go('#/dep/center');
};

/* ---- 集群监控（组件/中间件/运行时 网络拓扑大屏） ---- */
/* 节点资源画像：基础值 + 渲染期微抖动（每次渲染计算一次，供大屏/悬浮/明细/详情复用） */
A._metricBase = {
  'master-01':{cpu:38, mem:47, disk:52},
  'node-01':{cpu:41, mem:56, disk:66},
  'node-02':{cpu:79, mem:63, disk:58},
  'node-03':{cpu:46, mem:59, disk:82},
  'edge-01':{cpu:12, mem:24, disk:38}
};
A._computeMetrics = function(){
  A._nodeMetrics = {};
  DB.servers.forEach(function(sv){
    var b = A._metricBase[sv.name] || {cpu:30, mem:40, disk:50};
    var j = sv.status==='online'? function(){ return Math.round((Math.random()-0.5)*6); } : function(){ return 0; };
    A._nodeMetrics[sv.id] = {
      cpu: Math.max(1, Math.min(99, b.cpu+j())),
      mem: Math.max(1, Math.min(99, b.mem+j())),
      disk: Math.max(1, Math.min(99, b.disk+j()))
    };
  });
  return A._nodeMetrics;
};
A._mState = function(sv, m){
  if(!sv || sv.status!=='online') return 'off';
  if(m.disk>=80) return 'disk';
  if(m.cpu>=75) return 'cpu';
  return 'ok';
};
/* 节点详情：三环形仪表 + 角色信息 + 运行任务数 + 最近告警 */
A.svDetail = function(id){
  if(!A._nodeMetrics) A._computeMetrics();
  var sv = DB.servers.find(function(x){return x.id===id;});
  var m = A._nodeMetrics[id], on = sv.status==='online';
  var comps = DB.components.filter(function(c){return c.status==='running' && c.nodes.join(',').indexOf(sv.ip)>=0;});
  var tasks = on? comps.length*2 + (parseInt(sv.ip.split('.')[3],10)%9) : 0;
  var als = DB.deployAlarms.filter(function(a){ return a.desc.indexOf(sv.ip)>=0 || comps.some(function(c){return c.name===a.comp;}); }).slice(0,3);
  function rc(kind, v){ return kind==='disk'? (v>=80?'#e5484d':v>=60?'#d97706':'#16a34a') : kind==='cpu'? (v>=75?'#d97706':'#1668dc') : (v>=85?'#d97706':'#7c3aed'); }
  var body = (on? '' : '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>节点离线（最后心跳 2026-09-11 18:02），以下为最后采集快照。</span></div>')
    + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;justify-items:center;margin-bottom:14px">'
    + '<div>'+Charts.ring(m.cpu, 92, rc('cpu',m.cpu), 'CPU 使用率')+'</div>'
    + '<div>'+Charts.ring(m.mem, 92, rc('mem',m.mem), '内存使用率')+'</div>'
    + '<div>'+Charts.ring(m.disk, 92, rc('disk',m.disk), '磁盘使用率')+'</div></div>'
    + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:5px 20px;font-size:12.5px;margin-bottom:13px">'
    + '<div>节点 IP：<span class="mono">'+sv.ip+'</span></div><div>角色：<b>'+sv.role+'</b></div>'
    + '<div>规格：'+sv.cpu+' / '+sv.mem+' / '+sv.disk+'</div><div>操作系统：'+sv.os+'</div>'
    + '<div>状态：'+(on? st('success'):st('offline'))+'</div>'
    + '<div>运行任务数：<b>'+tasks+'</b> 个</div></div>'
    + '<div style="font-size:12px;color:var(--text-2);margin-bottom:6px">承载组件（'+comps.length+'）</div>'
    + (comps.length? comps.map(function(c){
        return '<div class="checker-line" style="margin-bottom:6px"><span style="width:8px;height:8px;border-radius:2px;background:#0891b2;flex-shrink:0"></span><b>'+c.name+'</b><span style="font-size:11px;color:var(--text-3)">v'+c.version+' · CPU '+c.cpu+'% / MEM '+c.mem+'%</span><span style="margin-left:auto">'+(c.health==='健康'? tag('健康','green'):tag(c.health,'orange'))+'</span></div>';
      }).join('') : '<div style="font-size:12px;color:var(--text-3);margin-bottom:8px">无运行组件</div>')
    + '<div style="font-size:12px;color:var(--text-2);margin:10px 0 6px">最近节点相关告警</div>'
    + (als.length? als.map(function(a){
        return '<div class="checker-line '+(a.status==='pending'?'err':'ok')+'" style="margin-bottom:6px"><span>'+(a.level==='err'?'✕':a.level==='warn'?'⚠':'ℹ')+'</span><b>'+a.title+'</b><span style="margin-left:auto;font-size:11px;color:var(--text-3)">'+a.time+'</span></div>';
      }).join('') : '<div style="font-size:12px;color:var(--text-3)">近 7 日无相关告警</div>');
  UI.modal({title:'节点详情 - '+sv.name+'（'+sv.ip+'）', w:'w-lg', body:body,
    footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="UI.closeModal();App.go(\'#/dep/log\')">查看节点日志</button>'});
};
/* ---- 运行拓扑数据构建：静态平台节点 + 组件节点（CP 关联），五层泳道 ---- */
A._topoBuild = function(metrics){
  var C = function(id){ return DB.components.find(function(x){return x.id===id;}); };
  var CP = {doris:C('CP01'), kafka:C('CP02'), flink:C('CP03'), zk:C('CP04'), redis:C('CP05'), mon:C('CP06')};
  var diskHot = DB.servers.some(function(s){ return s.status==='online' && metrics[s.id] && metrics[s.id].disk>=80; });
  var st = function(c){ return (!c || c.status!=='running')? 'idle' : 'success'; };
  var sub = function(c, extra){ return c.status==='running'? (extra? extra+' · ':'')+c.nodes.length+' 实例 · v'+c.version : '未部署'; };
  var cfg = function(c){
    if(!c || c.status!=='running') return {状态:'未部署 · 可在部署中心一键安装'};
    var o = {角色:c.role, 版本:'v'+c.version, 负载:'CPU '+c.cpu+'% · 内存 '+c.mem+'%', 健康度:c.health, 连续运行:c.upDays+' 天', 部署节点:c.nodes.join('  ')};
    if(c.qps) o.QPS = c.qps;
    return o;
  };
  var X=[60,320,580,840,1100], Y=[56,190,324,458,592];
  var nodes = [
    /* 接入层 */
    {id:'portal', name:'数据门户前端', type:'Web 入口', icon:'⌂', color:'#475569', x:X[0], y:Y[0], status:'success', sub:'2 实例 · v2.3.0', summary:'统一门户：开发中心 / 资产地图 / 运维中心前端，静态资源由 Nginx 分发', cfg:{实例:'portal-01 / portal-02', 版本:'v2.3.0', 端口:'80 / 443'}, host:'SV01'},
    {id:'nginx', name:'Nginx 负载均衡', type:'接入层', icon:'⇄', color:'#0ea5e9', x:X[1], y:Y[0], status:'success', sub:'主备双活', summary:'反向代理 / TLS 终结 / 会话保持 / 限流熔断', cfg:{部署模式:'Keepalived 主备', VIP:'192.168.30.100', 当前连接:'1,284', 转发QPS:'360'}, host:'SV01'},
    {id:'gateway', name:'API 网关', type:'接入层', icon:'⛨', color:'#0891b2', x:X[2], y:Y[0], status:'success', sub:'2 实例', summary:'统一 API 网关：认证鉴权、路由转发、灰度发布、审计埋点', cfg:{认证方式:'Token / LDAP', 路由规则:'38 条', 超时时间:'30s', 平均RT:'46ms'}, host:'SV01'},
    /* 运行时 · 平台应用服务 */
    {id:'svcapi', name:'平台核心服务', type:'运行时 · 应用服务', icon:'⚙', color:'#1668dc', x:X[0], y:Y[1], big:true, status:'success', sub:'2 实例 · v2.3.0', summary:'元数据 / 建模 / 质量 / 标准 / 资产引擎统一服务层', cfg:{服务:'元数据 · 质量 · 标准 · 资产', 实例:'svc-01 / svc-02', JVM:'8G · G1GC', 配置库:'万里 GreatDB', 缓存:'Redis'}, host:'SV01'},
    {id:'sched', name:'调度中心 DolphinScheduler', type:'运行时 · 调度', icon:'⏱', color:'#7c3aed', x:X[1], y:Y[1], big:true, status:'success', sub:'1 Master · 3 Worker', summary:'工作流定时调度 / 依赖编排 / 补数重跑 / 失败告警', cfg:{Master:'master-01', Worker:'node-01 / 02 / 03', 注册中心:'ZooKeeper', 今日实例:'42（成功 39 · 失败 3）'}, host:'SV01'},
    {id:'ide', name:'数据开发 IDE', type:'运行时 · 开发工具', icon:'⌨', color:'#2563eb', x:X[2], y:Y[1], status:'success', sub:'2 实例 · v2.3.0', summary:'SQL / 脚本在线开发：调试运行、版本管理、一键发布调度', cfg:{在线会话:'6 个', 支持引擎:'Doris SQL / Flink SQL', 版本:'v2.3.0'}, host:'SV01'},
    {id:'monitor', name:'Prometheus + Grafana', type:'运行时 · 可观测', icon:'◔', color:'#d97706', x:X[3], y:Y[1], status:st(CP.mon), sub:sub(CP.mon), cp:'CP06', summary:'指标采集 / 可视化大盘 / 告警规则与通知渠道', cfg:cfg(CP.mon)},
    /* 中间件 */
    {id:'kafka', name:'Kafka', type:'中间件 · 消息队列', icon:'❯', color:'#0d9488', x:X[0], y:Y[2], status:st(CP.kafka), sub:sub(CP.kafka), cp:'CP02', summary:'实时消息总线：CDC / 埋点 / 流任务输入（topic_order_pay 等）', cfg:cfg(CP.kafka)},
    {id:'zk', name:'ZooKeeper', type:'中间件 · 协调服务', icon:'✦', color:'#059669', x:X[1], y:Y[2], status:st(CP.zk), sub:sub(CP.zk), cp:'CP04', summary:'分布式协调：调度 Master 选举、配置发布通知', cfg:cfg(CP.zk)},
    {id:'redis', name:'Redis', type:'中间件 · 缓存', icon:'⚡', color:'#dc2626', x:X[2], y:Y[2], status:st(CP.redis), sub:sub(CP.redis), cp:'CP05', summary:'会话缓存 / 热点数据 / 分布式锁', cfg:cfg(CP.redis)},
    {id:'cfgdb', name:'万里 GreatDB 配置库', type:'中间件 · 配置存储', icon:'⛁', color:'#c2410c', x:X[3], y:Y[2], status:'success', sub:'主从 · v8.0', summary:'平台元数据与配置持久化（信创数据库）', cfg:{部署模式:'主从半同步', 数据量:'12.6 GB', TPS:'240', 备份策略:'每日 03:00 全量'}, host:'SV01'},
    {id:'rmq', name:'RocketMQ', type:'中间件 · 消息队列（国产备选）', icon:'✉', color:'#94a3b8', x:X[4], y:Y[2], state:'idle', status:'idle', plan:'国产化改造专项', summary:'Kafka 国产化备选方案，信创改造阶段评估中', cfg:{状态:'未部署 · 评估中'}},
    /* 计算引擎 */
    {id:'flink', name:'Flink 流计算', type:'计算引擎', icon:'≋', color:'#16a34a', x:X[0], y:Y[3], big:true, status:st(CP.flink), sub:sub(CP.flink,'JM×1 · TM×2'), cp:'CP03', summary:'实时入仓 / 分钟聚合 / CDC 加工（SJ001-SJ004）', cfg:cfg(CP.flink)},
    {id:'dorisfe', name:'Doris FE', type:'计算引擎 · OLAP', icon:'◈', color:'#2563eb', x:X[1], y:Y[3], status:'success', sub:'FE ×1 · v2.1.6', cp:'CP01', summary:'SQL 解析 / 查询规划 / 元数据管理', cfg:{角色:'Leader FE', 活跃连接:'86', 查询延迟:'P95 320ms'}},
    {id:'spark', name:'Spark', type:'计算引擎 · 批处理', icon:'★', color:'#94a3b8', x:X[2], y:Y[3], state:'idle', status:'idle', plan:'离线数仓套件 SU02', summary:'离线批加工引擎，随离线数仓套件一并部署', cfg:{状态:'未部署 · 随 SU02'}},
    /* 存储 */
    {id:'dorisbe', name:'Doris BE 存储', type:'存储 · 列存引擎', icon:'▦', color:'#1668dc', x:X[0], y:Y[4], big:true, status: diskHot? 'warn':'success', sub:'BE ×3 · v2.1.6', cp:'CP01', summary:'tablet 存储 / 副本 / Compaction；node-03 磁盘 82% 告警（PA01）', cfg:{副本策略:'3 副本', tablet总数:'18,204', 磁盘告警: diskHot? 'node-03 82%（PA01 待处置）':'无', Compaction:'正常'}},
    {id:'hdfs', name:'HDFS + Hive', type:'存储 · 离线数仓', icon:'▩', color:'#94a3b8', x:X[1], y:Y[4], state:'idle', status:'idle', plan:'离线数仓套件 SU02', summary:'离线数仓底座，随离线数仓套件一并部署', cfg:{状态:'未部署 · 随 SU02'}}
  ];
  var edges = [
    {from:'portal', to:'nginx'}, {from:'nginx', to:'gateway'}, {from:'gateway', to:'svcapi'},
    {from:'svcapi', to:'sched', label:'工作流编排'}, {from:'ide', to:'sched', label:'提交任务'},
    {from:'svcapi', to:'redis', label:'会话 / 热点缓存'}, {from:'svcapi', to:'cfgdb', label:'配置 / 元数据读写'},
    {from:'sched', to:'zk', label:'注册 / 选主'},
    {from:'monitor', to:'svcapi', kind:'dep', label:'指标采集'}, {from:'monitor', to:'flink', kind:'dep', label:'指标采集'},
    {from:'kafka', to:'flink', label:'消费 Topic'}, {from:'sched', to:'flink', label:'流任务下发'},
    {from:'flink', to:'dorisfe', label:'Sink 写入'}, {from:'dorisfe', to:'dorisbe', label:'Tablet 读写'},
    {from:'sched', to:'spark', kind:'dep', label:'SU02 规划'}, {from:'spark', to:'hdfs', kind:'dep', label:'扩展预留'},
    {from:'kafka', to:'rmq', kind:'dep', label:'国产化备选'}
  ];
  var bands = [
    {y:16, h:112, label:'接入层 · 用户与入口', sub:'门户 / 负载均衡 / API 网关'},
    {y:150, h:112, label:'运行时 · 平台应用服务', sub:'核心服务 / 调度中心 / IDE / 可观测'},
    {y:284, h:112, label:'中间件 · 消息 / 协调 / 缓存 / 配置', sub:'Kafka · ZooKeeper · Redis · GreatDB'},
    {y:418, h:112, label:'计算引擎层', sub:'Flink 流计算 / Doris FE / Spark 批处理'},
    {y:552, h:112, label:'数据存储层', sub:'Doris BE 列存 / HDFS（规划）'}
  ];
  var map = {}; nodes.forEach(function(n){ map[n.id]=n; });
  return {nodes:nodes, edges:edges, bands:bands, map:map};
};
/* 拓扑节点详情弹窗：组件实例画像 / 运行时配置 / 未部署引导，闭环运维入口 */
A.topoNode = function(id){
  var d = A._topoData, n = d && d.map[id]; if(!n) return;
  if(n.state==='idle'){
    UI.modal({title:'节点详情 - '+n.name, w:'w-md', body:
      '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>「'+UI.esc(n.name)+'」当前未部署'+(n.plan? '，规划随「'+n.plan+'」一并交付':'')+'。</span></div>'
      +'<div style="font-size:12.5px;color:var(--text-2);line-height:1.9">'+UI.esc(n.summary||'')+'</div>'
      +'<div class="checker-line" style="margin-top:10px"><span>ℹ</span><b>部署入口</b><span style="margin-left:auto">部署中心 → 一键部署向导 / 部署套件</span></div>',
      footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="UI.closeModal();App.go(\'#/dep/center\')">前往部署中心</button>'});
    return;
  }
  var c = n.cp? DB.components.find(function(x){return x.id===n.cp;}) : null;
  if(c){
    var als = DB.deployAlarms.filter(function(a){ return a.comp===c.name || (a.desc||'').indexOf(c.name)>=0; }).slice(0,3);
    var hosts = c.nodes.map(function(hn){
      var ip = hn.split('(')[0];
      var sv = DB.servers.find(function(x){return x.ip===ip;});
      return '<span class="mono" onclick="'+(sv? 'UI.closeModal();A.svDetail(\''+sv.id+'\')':'UI.toast(\'离线节点：快照数据（原型演示）\',\'info\')')+'" style="display:inline-block;padding:4px 10px;margin:0 8px 8px 0;border:1px solid var(--border);border-radius:6px;font-size:11px;background:#f8fafc;cursor:pointer">'+UI.esc(hn)+'</span>';
    }).join('');
    var mr = [['CPU', c.cpu+'%'], ['内存', c.mem+'%'], ['QPS', c.qps? c.qps:'—'], ['实例', c.nodes.length+' 个']];
    UI.modal({title:'组件详情 - '+c.name, w:'w-lg', body:
      '<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">'
      +'<span class="type-icon" style="background:'+n.color+'18;color:'+n.color+';width:42px;height:42px;font-size:19px">'+n.icon+'</span>'
      +'<div style="flex:1"><b style="font-size:14.5px">'+c.name+'</b><div style="font-size:11.5px;color:var(--text-3);margin-top:2px">'+UI.esc(c.role)+' · v'+c.version+' · 连续运行 '+c.upDays+' 天</div></div>'
      +(c.health==='健康'? tag('健康','green'):tag(c.health,'orange'))+'</div>'
      +'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px">'
      + mr.map(function(x){return '<div style="border:1px solid var(--border);border-radius:8px;padding:8px 10px;text-align:center"><div style="font-size:16px;font-weight:700;color:var(--primary)">'+x[1]+'</div><div style="font-size:10.5px;color:var(--text-3)">'+x[0]+'</div></div>';}).join('')+'</div>'
      +'<div style="font-size:12px;color:var(--text-2);margin-bottom:7px">实例分布 <span style="color:var(--text-3)">（点击主机查看资源画像）</span></div><div>'+hosts+'</div>'
      +'<div style="font-size:12px;color:var(--text-2);margin:12px 0 7px">相关告警（近 7 日）</div>'
      +(als.length? als.map(function(a){ return '<div class="checker-line '+(a.status==='pending'?'err':'ok')+'" style="margin-bottom:6px"><span>'+(a.level==='err'?'✕':a.level==='warn'?'⚠':'ℹ')+'</span><b>'+a.title+'</b><span style="margin-left:auto;font-size:11px;color:var(--text-3)">'+a.time+'</span></div>'; }).join('') : '<div style="font-size:12px;color:var(--text-3)">近 7 日无相关告警</div>'),
      footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>'
      +'<button class="btn" onclick="UI.toast(\'配置管理：'+UI.esc(c.name)+' 参数（原型演示）\',\'info\')">配置</button>'
      +'<button class="btn" onclick="UI.closeModal();App.go(\'#/dep/log\')">组件日志</button>'
      +'<button class="btn btn-danger" onclick="A.cpRestart(\''+c.id+'\')">滚动重启</button>'});
    return;
  }
  /* 平台运行时节点（非 CP 组件） */
  var rows = Object.keys(n.cfg||{}).map(function(k){
    return '<div class="checker-line" style="margin-bottom:6px"><span style="width:8px;height:8px;border-radius:2px;background:'+n.color+';flex-shrink:0"></span><b>'+UI.esc(k)+'</b><span style="margin-left:auto" class="mono">'+UI.esc(String(n.cfg[k]))+'</span></div>';
  }).join('');
  UI.modal({title:'运行时详情 - '+n.name, w:'w-md', body:
    '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">'
    +'<span class="type-icon" style="background:'+n.color+'18;color:'+n.color+';width:38px;height:38px;font-size:17px">'+n.icon+'</span>'
    +'<div style="flex:1"><b style="font-size:14px">'+UI.esc(n.name)+'</b><div style="font-size:11.5px;color:var(--text-3)">'+UI.esc(n.type)+' · '+UI.esc(n.sub||'')+'</div></div>'+tag('运行中','green')+'</div>'
    +'<div class="f-help" style="margin-bottom:10px">'+UI.esc(n.summary||'')+'</div>'+rows,
    footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>'
    +(n.host? '<button class="btn btn-primary" onclick="UI.closeModal();A.svDetail(\''+n.host+'\')">承载主机详情</button>':'')});
};
App.reg('#/dep/monitor', '集群监控', function(){
  var metrics = A._computeMetrics();
  var online = DB.servers.filter(function(s){return s.status==='online';});
  var avg = function(k){ return online.length? Math.round(online.reduce(function(s,s2){return s+metrics[s2.id][k];},0)/online.length) : 0; };
  var diskAlarms = DB.servers.filter(function(s){return s.status==='online' && metrics[s.id].disk>=80;}).length;
  var compRun = DB.components.filter(function(c){return c.status==='running';}).length;
  var html = UI.pageHead('集群运行拓扑大屏',
    '组件 / 中间件 / 运行时 网络拓扑具象化：五层泳道 · 调用与依赖链路 · 实例健康与资源水位（Prometheus 采集，15s 周期）',
    '<button class="btn" onclick="UI.toast(\'拓扑与指标已刷新\',\'success\');App.resolve()">刷新</button>'
    +'<button class="btn" onclick="App.go(\'#/dep/alarm\')">告警管理</button>');
  /* 顶部统计条 */
  html += '<div class="grid" style="grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#475569">▤</span><div><div class="stat-num">'+DB.servers.length+'</div><div class="stat-label">主机节点</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+online.length+'/'+DB.servers.length+'</div><div class="stat-label">节点在线</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#1668dc">⚙</span><div><div class="stat-num">'+compRun+'/'+DB.components.length+'</div><div class="stat-label">组件运行中</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#7c3aed">◔</span><div><div class="stat-num">'+avg('cpu')+'% / '+avg('mem')+'%</div><div class="stat-label">CPU / 内存均值</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#e5484d">⚑</span><div><div class="stat-num">'+diskAlarms+'</div><div class="stat-label">磁盘告警节点（≥80%）</div></div></div></div>';
  /* 左（62%）：运行网络拓扑   右（38%）：运行资源 */
  A._topoData = A._topoBuild(metrics);
  var legend = '<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:11.5px;color:var(--text-2);margin-bottom:10px;align-items:center">'
    +'<span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#16a34a;margin-right:5px;vertical-align:middle"></i>健康</span>'
    +'<span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#f59e0b;margin-right:5px;vertical-align:middle"></i>资源告警</span>'
    +'<span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:#94a3b8;margin-right:5px;vertical-align:middle"></i>未部署 / 规划</span>'
    +'<span><i style="display:inline-block;width:18px;height:0;border-top:2px solid #7aa2f7;margin-right:5px;vertical-align:middle"></i>调用 / 数据流</span>'
    +'<span><i style="display:inline-block;width:18px;height:0;border-top:2px dashed #94a3b8;margin-right:5px;vertical-align:middle"></i>依赖 / 规划</span>'
    +'<span style="margin-left:auto;color:var(--text-3)">悬停看实例摘要 · 点击节点看详情与运维操作</span></div>';
  var diskSpec = {'master-01':2,'node-01':4,'node-02':4,'node-03':4,'edge-01':1};
  var storeItems = DB.servers.map(function(sv){
    var m = metrics[sv.id], total = diskSpec[sv.name]||2;
    var it = {name:sv.name, value:+(total*m.disk/100).toFixed(2), max:total, suffix:' /'+total+'T'};
    if(sv.status!=='online') it.color = 'linear-gradient(90deg,#94a3b8,#cbd5e1)';
    else if(m.disk>=80) it.color = 'linear-gradient(90deg,#e5484d,#f87171)';
    return it;
  });
  var svcDefs = [
    {n:'平台核心服务', r:'运行时 · API / 引擎服务', inst:'2 实例', ver:'v2.3.0', builtin:1},
    {n:'调度中心 DolphinScheduler', r:'运行时 · 工作流调度', inst:'1M + 3W', ver:'v3.2.0', builtin:1},
    {n:'数据开发 IDE', r:'运行时 · 在线开发', inst:'2 实例', ver:'v2.3.0', builtin:1},
    {n:'Apache Doris', r:'OLAP 引擎', ref:'CP01'},
    {n:'Flink', r:'流计算引擎', ref:'CP03'},
    {n:'Kafka', r:'消息队列', ref:'CP02'},
    {n:'ZooKeeper', r:'协调服务', ref:'CP04'},
    {n:'Redis', r:'缓存', ref:'CP05'},
    {n:'Prometheus + Grafana', r:'监控告警', ref:'CP06'},
    {n:'RocketMQ', r:'消息队列 · 国产备选', ref:'CP07'},
    {n:'HDFS + Hive', r:'离线数仓（规划）', ref:'CP08'}
  ];
  var svcRows = svcDefs.map(function(s){
    var c = s.ref? DB.components.find(function(x){return x.id===s.ref;}) : null;
    var run = s.builtin? true : !!(c && c.status==='running');
    return '<div style="display:flex;align-items:center;gap:8px;padding:6px 2px;border-bottom:1px dashed var(--border);font-size:12px">'
      +'<span style="width:8px;height:8px;border-radius:2px;background:'+(run?'#16a34a':'#cbd5e1')+';flex-shrink:0"></span>'
      +'<span style="flex:1"><b>'+s.n+'</b><span style="font-size:11px;color:var(--text-3)"> · '+s.r+'</span></span>'
      +(run? tag('运行中','green') : tag('未部署','gray'))
      +'<span style="width:60px;text-align:right;color:var(--text-2)">'+(run? (s.inst || c.nodes.length+' 实例'):'—')+'</span>'
      +'<span class="mono" style="width:66px;text-align:right">'+(run? (s.ver || 'v'+c.version):'—')+'</span></div>';
  }).join('');
  var right = UI.card('集群 CPU / 内存 8 小时趋势', '<div style="display:flex;gap:16px;font-size:11.5px;color:var(--text-2);margin-bottom:2px">'
      +'<span><i style="display:inline-block;width:12px;height:3px;background:#1668dc;border-radius:2px;margin-right:5px;vertical-align:middle"></i>CPU 均值 %</span>'
      +'<span><i style="display:inline-block;width:12px;height:3px;background:#7c3aed;border-radius:2px;margin-right:5px;vertical-align:middle"></i>内存均值 %</span></div>'
      + Charts.line({w:380, h:200, labels:['15:00','16:00','17:00','18:00','19:00','20:00','21:00','22:00'], series:[
        {name:'CPU', color:'#1668dc', data:[42,45,44,49,53,58,55,51]},
        {name:'内存', color:'#7c3aed', data:[55,56,57,57,60,62,61,60]}]}))
    + UI.card('存储容量（已用 / 总量 · by 主机）', Charts.hbars(storeItems)
      + '<div style="font-size:11px;color:var(--text-3);margin-top:8px">node-03 磁盘 82% 超阈值（PA01 待处置），建议执行「磁盘清理」；edge-01 离线，容量为最后快照。</div>')
    + UI.card('服务运行清单', '<div style="display:flex;font-size:11px;color:var(--text-3);padding:0 2px 6px;border-bottom:1px solid var(--border)">'
      +'<span style="flex:1">服务 / 组件</span><span style="width:60px">状态</span><span style="width:58px;text-align:right">实例</span><span style="width:66px;text-align:right">版本</span></div>'
      + svcRows);
  html += '<div style="display:grid;grid-template-columns:62fr 38fr;gap:16px;align-items:start">'
    + UI.card('运行网络拓扑 · 五层泳道（接入 → 运行时 → 中间件 → 计算 → 存储）', legend+'<div id="depTopoMount"></div>')
    + '<div>'+right+'</div></div>';
  /* 主机资源明细 */
  html += UI.card('主机资源明细', UI.tbl({
    id:'t_sv', rowKey:'id', pageSize:6, searchKeys:['id','name','ip'], searchPh:'搜索主机',
    data:function(){ return DB.servers; },
    cols:[
      {t:'主机', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.ip+' · '+r.role+'</div>';}},
      {t:'规格', render:function(r){return r.cpu+' / '+r.mem+' / '+r.disk;}},
      {t:'系统', k:'os'},
      {t:'承载组件', render:function(r){
        var cs = DB.components.filter(function(c){return c.status==='running' && c.nodes.join(',').indexOf(r.ip)>=0;});
        return cs.length? '<span style="font-size:11.5px">'+cs.map(function(c){return c.name;}).join('、')+'</span>' : '<span style="color:var(--text-3)">—</span>';}},
      {t:'资源使用', render:function(r){
        if(r.status!=='online') return '<span style="color:var(--text-3)">离线</span>';
        var m = A._nodeMetrics[r.id];
        var cls = m.disk>=80? ' red' : (m.disk>=60? ' orange':'');
        return '<div class="mini-bar-cell"><div class="progress'+cls+'" style="width:110px"><div class="bar" style="width:'+m.disk+'%"></div></div><span style="font-size:11px;color:var(--text-3)">CPU '+m.cpu+'% · MEM '+m.mem+'% · DISK '+m.disk+'%</span></div>';}},
      {t:'状态', render:function(r){return st(r.status==='online'?'success':'offline');}}
    ],
    ops:function(r){ return '<a onclick="A.svDetail(\''+r.id+'\')">详情</a><a onclick="App.go(\'#/dep/log\')">日志</a>'; }}));
  return html;
});
/* 拓扑画布渲染（页面注入后挂载 VC）+ 定位高亮消费 */
App.onAfterRender(function(){
  if(location.hash.indexOf('#/dep/monitor')!==0) return;
  if(!document.getElementById('depTopoMount') || !A._topoData) return;
  A._topoVc = VC.create({mount:'depTopoMount', nodes:A._topoData.nodes, edges:A._topoData.edges, bands:A._topoData.bands,
    mode:'view', legend:false, height:660, onNodeClick:function(n){ A.topoNode(n.id); }});
  if(A._topoPending && A._topoPending.length){
    var ids = A._topoPending.slice(); A._topoPending = null;
    setTimeout(function(){
      ids.forEach(function(id){ VC.highlight(A._topoVc, id); });
      UI.toast('已高亮 '+ids.length+' 个与该主机关联的拓扑节点', 'success');
    }, 150);
  }
});

/* ---- 组件日志 ---- */
App.reg('#/dep/log', '组件日志', function(){
  var html = UI.pageHead('组件日志', '部署与运行日志聚合：按组件/级别筛选，支持检索与下载');
  html += UI.card('日志流', UI.tbl({
    id:'t_dl', rowKey:'id', pageSize:10, searchKeys:['id','comp','content'], searchPh:'搜索日志内容',
    filters:[
      {k:'comp', label:'组件', options:DB.components.map(function(c){return {v:c.name,t:c.name};})},
      {k:'level', label:'级别', options:[{v:'INFO',t:'INFO'},{v:'WARN',t:'WARN'},{v:'ERROR',t:'ERROR'}]}
    ],
    data:function(){ return DB.deployLogs; },
    cols:[
      {t:'时间', k:'time', render:function(r){return '<span class="mono" style="font-size:11.5px">'+r.time+'</span>';}},
      {t:'组件', k:'comp', render:function(r){return tag(r.comp, 'blue');}},
      {t:'节点', k:'node', render:function(r){return '<span class="mono" style="font-size:11.5px">'+r.node+'</span>';}},
      {t:'级别', k:'level', render:function(r){return '<span class="tag '+(r.level==='ERROR'?'tag-red':r.level==='WARN'?'tag-orange':'tag-gray')+'" style="height:17px">'+r.level+'</span>';}},
      {t:'内容', k:'content', render:function(r){return '<span class="mono" style="font-size:11.5px">'+UI.esc(r.content)+'</span>';}}
    ],
    ops:function(r){ return r.level==='ERROR'? '<a onclick="App.go(\'#/dep/ops\')">去处置</a>':'<a onclick="UI.toast(\'日志已复制\',\'info\')">复制</a>'; }}));
  return html;
});

/* ---- 告警管理 ---- */
App.reg('#/dep/alarm', '告警管理', function(){
  var html = UI.pageHead('部署运维告警', '基础设施告警：磁盘/消费积压/Checkpoint 等，待处理告警需闭环处置',
    '<button class="btn" onclick="App.go(\'#/dep/ops\')">运维操作</button>');
  html += '<div class="grid grid-3" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#d97706">⚑</span><div><div class="stat-num">'+DB.deployAlarms.filter(function(a){return a.status==='pending';}).length+'</div><div class="stat-label">待处理告警</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+DB.deployAlarms.filter(function(a){return a.status==='fixed';}).length+'</div><div class="stat-label">已恢复</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#475569">⇩</span><div><div class="stat-num">'+DB.deployAlarms.length+'</div><div class="stat-label">告警总数（今日）</div></div></div></div>';
  html += UI.card('告警列表', UI.tbl({
    id:'t_pa', rowKey:'id', pageSize:8, searchKeys:['id','comp','title'], searchPh:'搜索告警',
    filters:[
      {k:'level', label:'级别', options:[{v:'err',t:'严重'},{v:'warn',t:'警告'},{v:'info',t:'提示'}]},
      {k:'status', label:'状态', options:[{v:'pending',t:'待处理'},{v:'fixed',t:'已恢复'}]}
    ],
    data:function(){ return DB.deployAlarms; },
    cols:[
      {t:'告警', k:'title', render:function(r){return '<div><b>'+r.title+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+UI.esc(r.desc)+'</div></div>';}},
      {t:'组件', k:'comp', render:function(r){return tag(r.comp,'blue');}},
      {t:'级别', k:'level', render:function(r){return '<span class="tag '+(r.level==='err'?'tag-red':r.level==='warn'?'tag-orange':'tag-gray')+'" style="height:17px">'+({err:'严重',warn:'警告',info:'提示'})[r.level]+'</span>';}},
      {t:'时间', k:'time'},
      {t:'渠道', k:'channel'},
      {t:'状态', k:'status', render:function(r){return st(r.status==='pending'?'pending':'recovered');}}
    ],
    ops:function(r){
      if(r.status==='pending') return '<a onclick="A.paHandle(\''+r.id+'\')">处置</a>';
      return '<a onclick="UI.toast(\''+UI.esc(r.desc)+'\',\'info\')">详情</a>';
    }}));
  return html;
});
A.paHandle = function(id){
  var a = DB.deployAlarms.find(function(x){return x.id===id;});
  UI.drawer({title:'告警处置 - '+a.title, w:'w-lg', body:
    '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>'+UI.esc(a.desc)+'</span></div>'
    + UI.fRadio('处置方式', 'pa_way', [{v:'auto',t:'确认自恢复（记录观察）'},{v:'scale',t:'扩容/清理（磁盘清理、并行度调整）'},{v:'ticket',t:'转运维工单'}], 'auto')
    + UI.fTextarea('处置说明', 'pa_note', {rows:2, req:true}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.paSave(\''+id+'\')">完成处置</button>'});
};
A.paSave = function(id){
  var a = DB.deployAlarms.find(function(x){return x.id===id;});
  if(!UI.val('pa_note')){ UI.toast('请填写处置说明', 'warn'); return; }
  a.status='fixed';
  UI.toast('告警已处置并恢复，观察期 24h', 'success'); App.resolve();
};

/* ---- 运维操作 ---- */
App.reg('#/dep/ops', '运维操作', function(){
  var html = UI.pageHead('运维操作', '高频运维动作：组件重启 / NTP校准 / 磁盘清理 / 配置下发，操作留痕审计',
    '<button class="btn" onclick="UI.toast(\'操作审计已导出（近7日 '+(12+DB.deployLogs.length)+' 条）\',\'success\')">操作审计</button>');
  var ops = [
    {t:'滚动重启组件', d:'按节点逐台重启，避免服务中断', ico:'↻', c:'#d97706', fn:'A.opRestart()'},
    {t:'NTP 时钟校准', d:'修复 node-03 时钟偏差 4.2s', ico:'⏱', c:'#1668dc', fn:'A.opNtp()'},
    {t:'磁盘清理', d:'清理 BE 临时文件与旧日志（node-03 82%）', ico:'🗑', c:'#e5484d', fn:'A.opDisk()'},
    {t:'配置下发', d:'修改组件参数并滚动生效', ico:'⚙', c:'#7c3aed', fn:'A.opConfig()'},
    {t:'健康巡检', d:'全组件健康检查（端口/进程/读写）', ico:'✓', c:'#16a34a', fn:'A.opCheck()'},
    {t:'备份立即执行', d:'手动触发配置库全量备份', ico:'⇩', c:'#0891b2', fn:'A.bkNow()'}
  ];
  html += '<div class="grid" style="grid-template-columns:repeat(3,1fr)">'
    + ops.map(function(o){
      return '<div class="stat-card hoverable" onclick="'+o.fn+'"><span class="type-icon" style="background:'+o.c+'">'+o.ico+'</span><div><b style="font-size:13px">'+o.t+'</b><div style="font-size:11px;color:var(--text-3)">'+o.d+'</div></div></div>';
    }).join('')+'</div>';
  /* 资产图表：组件版本分布环形图 + 许可证/到期台账 */
  var verPalette = ['#1668dc','#0d9488','#d97706','#7c3aed','#e5484d','#0891b2'];
  var verItems = [], verLegend = '';
  DB.components.forEach(function(c){
    if(c.status!=='running') return;
    var col = verPalette[verItems.length % verPalette.length];
    verItems.push({name:c.name+' v'+c.version, value:1, color:col});
    verLegend += '<div style="display:flex;align-items:center;gap:7px;font-size:11.5px;margin-bottom:7px"><span style="width:9px;height:9px;border-radius:3px;background:'+col+';flex-shrink:0"></span><span style="flex:1">'+c.name+'</span><span class="mono">v'+c.version+'</span><span style="color:var(--text-3)">×1</span></div>';
  });
  var undepCnt = DB.components.filter(function(c){return c.status!=='running';}).length;
  verItems.push({name:'未安装', value:undepCnt, color:'#cbd5e1'});
  verLegend += '<div style="display:flex;align-items:center;gap:7px;font-size:11.5px;margin-bottom:7px"><span style="width:9px;height:9px;border-radius:3px;background:#cbd5e1;flex-shrink:0"></span><span style="flex:1">未安装</span><span class="mono">—</span><span style="color:var(--text-3)">×'+undepCnt+'</span></div>';
  var lics = [
    {name:'Doris / Kafka / Flink / ZK 开源授权', type:'Apache-2.0', exp:'永久有效', stt:'ok'},
    {name:'万里数据库适配认证', type:'商业授权', exp:'2027-06-30 到期', stt:'ok'},
    {name:'Kafka 商业支持订阅（原厂服务）', type:'厂商订阅', exp:'2026-12-20 到期', stt:'ok'},
    {name:'鲲鹏加速库授权（BIOS/驱动）', type:'商业授权', exp:'2026-10-08 到期', stt:'soon'},
    {name:'旧版监控平台 License', type:'商业授权', exp:'2026-08-31 已过期', stt:'expired'}
  ];
  var licTag = {ok:tag('有效','green'), soon:tag('即将到期','orange'), expired:tag('已过期','red')};
  html += '<div class="grid" style="grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">'
    + UI.card('资产图表 · 组件版本分布', '<div style="display:flex;gap:22px;align-items:center">'
      + '<div style="flex:1">'+Charts.donut({items:verItems, size:170, center:(DB.components.length-undepCnt)+'/'+DB.components.length, centerLabel:'已部署 / 组件总数'})+'</div>'
      + '<div style="flex:1.2">'+verLegend+'</div></div>')
    + UI.card('资产图表 · 许可证 / 到期管理', lics.map(function(l){
        return '<div class="checker-line" style="margin-bottom:8px"><span style="width:8px;height:8px;border-radius:2px;flex-shrink:0;background:'+(l.stt==='ok'?'#16a34a':l.stt==='soon'?'#d97706':'#e5484d')+'"></span>'
          +'<div style="flex:1"><b>'+l.name+'</b><div style="font-size:11px;color:var(--text-3)">'+l.type+' · '+l.exp+'</div></div>'+licTag[l.stt]+'</div>';
      }).join('')
      + '<div style="font-size:11px;color:var(--text-3);margin-top:2px">许可证台账与到期提醒（演示数据）；鲲鹏加速库授权 25 天内到期，建议提前发起续购。</div>')
    + '</div>';
  html += UI.card('最近运维记录', UI.timeline([
    {cls:'ok', title:'Kafka 分区再均衡完成', time:'2026-09-12 21:40', body:'topic_order_pay 6 分区，由 王工 执行'},
    {cls:'warn', title:'Doris tablet 副本自动修复', time:'2026-09-12 21:38', body:'tablet 10230 副本恢复健康（自愈）'},
    {cls:'err', title:'Doris FE 心跳超时（自恢复）', time:'2026-09-12 21:30', body:'BE 10002 心跳超时重试成功，建议观察'},
    {cls:'ok', title:'Flink Checkpoint 恢复正常', time:'2026-09-12 17:45', body:'SJ002 扩并行度 4→8 后 checkpoint 42s→8s'}]));
  return html;
});
A.opRestart = function(){
  UI.drawer({title:'滚动重启组件', w:'w-md', body:
    UI.fSelect('组件', 'op_comp', DB.components.filter(function(c){return c.status==='running';}).map(function(c){return {v:c.name,t:c.name};}), {})
    + '<div class="lock-tip">滚动策略：逐节点重启，节点健康检查通过后再继续下一台。</div>',
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-danger" onclick="A.opRestartGo()">确认重启</button>'});
};
A.opRestartGo = function(){
  var name = UI.val('op_comp');
  UI.closeDrawer();
  UI.toast('开始滚动重启 '+name+'（3 节点）...', 'info');
  setTimeout(function(){ UI.toast(name+' 滚动重启完成，健康检查通过', 'success'); }, 1600);
};
A.opNtp = function(){
  UI.toast('正在对 node-03 执行 NTP 校准（chronyc makestep）...', 'info');
  setTimeout(function(){ UI.toast('校准完成：偏差 4.2s → 0.003s', 'success'); }, 1200);
};
A.opDisk = function(){
  UI.confirm({title:'磁盘清理', danger:true, msg:'清理 BE 临时文件与 7 天前日志？', detail:'预计释放 60GB（node-03），不影响业务数据。', onOk:function(){
    setTimeout(function(){ UI.toast('清理完成：磁盘使用率 82% → 61%', 'success');
      var a = DB.deployAlarms.find(function(x){return x.id==='PA01';}); if(a){ a.status='fixed'; }
      App.resolve();
    }, 1300);
  }});
};
A.opConfig = function(){
  UI.drawer({title:'配置下发', w:'w-md', body:
    UI.fSelect('组件', 'cf_comp', DB.components.filter(function(c){return c.status==='running';}).map(function(c){return {v:c.name,t:c.name};}), {})
    + UI.fTextarea('配置片段', 'cf_body', {rows:4, mono:true, ph:'如：be.conf\nmem_limit = 80%'})
    + UI.fSwitch('滚动生效（逐节点重启）', 'cf_roll', true),
    onOk:function(){
      UI.toast('配置已下发并滚动生效', 'success');
    }});
};
A.opCheck = function(){
  UI.toast('正在执行全组件健康巡检...', 'info');
  setTimeout(function(){
    var items = DB.components.filter(function(c){return c.status==='running';}).map(function(c){
      return '<div class="checker-line ok"><span>✓</span><b>'+c.name+'</b><span style="margin-left:auto">端口/进程/读写 正常</span></div>';
    }).join('');
    UI.modal({title:'健康巡检结果', w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:items});
  }, 1200);
};
})();
