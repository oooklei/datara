/* ============================================================
   Datara 原型 · 核心框架（路由/布局/通用组件/SVG图表）
   ============================================================ */
var App = {
  routes: {},          // path -> {title, render(params)}
  pageActions: {},     // 每页动作注册表（挂到 A 上）
  _hooks: [],          // 每次路由渲染后执行的钩子队列（App.onAfterRender）
  cur: null,

  reg: function(path, title, render){ this.routes[path] = {title:title, render:render}; },
  go: function(path){ if(location.hash === path){ this.resolve(); } else { location.hash = path; } },

  boot: function(){
    this.renderLayout();
    window.addEventListener('hashchange', function(){ App.resolve(); });
    if(!location.hash) location.hash = '#/dashboard';
    else this.resolve();
  },

  matchRoute: function(){
    var h = location.hash || '#/dashboard';
    var q = null;
    var qIdx = h.indexOf('?');
    if(qIdx >= 0){ q = h.slice(qIdx+1); h = h.slice(0, qIdx); }
    if(App.routes[h]) return {route:App.routes[h], params:{}, query:q, path:h};
    // 参数路由 :id
    var segs = h.split('/');
    for(var p in App.routes){
      var ps = p.split('/');
      if(ps.length !== segs.length) continue;
      var params = {}, ok = true;
      for(var i=0;i<ps.length;i++){
        if(ps[i].charAt(0) === ':') params[ps[i].slice(1)] = decodeURIComponent(segs[i]);
        else if(ps[i] !== segs[i]){ ok = false; break; }
      }
      if(ok) return {route:App.routes[p], params:params, query:q, path:h};
    }
    return null;
  },

  resolve: function(){
    var m = this.matchRoute();
    var box = document.getElementById('page-root');
    if(!m){ box.innerHTML = '<div class="empty"><span class="e-ico">⚠</span><p>页面不存在</p><a onclick="location.hash=\'#/dashboard\'">返回工作台</a></div>'; return; }
    this.cur = m;
    // 面包屑
    document.getElementById('crumb').innerHTML = this.buildCrumb(m.path);
    // 菜单激活态
    this.markMenu(m.path);
    // 渲染
    box.className = 'page-fade';
    try { box.innerHTML = m.route.render(m.params, m.query); }
    catch(e){ box.innerHTML = '<div class="empty"><span class="e-ico">✗</span><p>页面渲染异常：'+e.message+'</p></div>'; console.error(e); }
    box.scrollIntoView && (document.getElementById('page-root').scrollTop = 0);
    // 页面后置钩子（图表、画布等）：App.onAfterRender 注册的队列 + 路由自带 mounted
    if(m.route.mounted) setTimeout(m.route.mounted, 0);
    App._hooks.forEach(function(f){ try{ f(m); }catch(e){ console.error(e); } });
  },

  onAfterRender: function(fn){ App._hooks.push(fn); },

  buildCrumb: function(path){
    var out = [];
    for(var g=0; g<MENUS.length; g++){
      var grp = MENUS[g];
      for(var i=0;i<grp.items.length;i++){
        var it = grp.items[i];
        if(it.path === path || (it.children && it.children.some(function(c){return c.path===path;}))){
          out.push('<span>'+grp.group+'</span><span class="sep">/</span><span>'+it.label+'</span>');
          if(it.path !== path) out.push('<span class="sep">/</span><b>'+path.split('/').pop()+'</b>');
          else out.push('<span class="sep">/</span><b>'+(it.children? it.children.filter(function(c){return c.path===path;})[0].label || it.label : it.label)+'</b>');
          return out.join('');
        }
      }
    }
    return '<b>'+(App.routes[path]? App.routes[path].title : '页面')+'</b>';
  },

  markMenu: function(path){
    document.querySelectorAll('.menu-item[data-path]').forEach(function(el){
      el.classList.remove('active');
      if(el.getAttribute('data-path') === path || el.getAttribute('data-prefix') && path.indexOf(el.getAttribute('data-prefix')) === 0) el.classList.add('active');
    });
  },

  renderLayout: function(){
    var menuHtml = MENUS.map(function(grp){
      var items = grp.items.map(function(it){
        if(it.children){
          var subs = it.children.map(function(c){
            return '<div class="menu-item" data-path="'+c.path+'" onclick="App.go(\''+c.path+'\')"><span class="ico">·</span><span class="lbl">'+c.label+'</span></div>';
          }).join('');
          return '<div class="menu-item has-sub" data-path="'+it.path+'" data-prefix="'+it.path.slice(0, it.path.lastIndexOf('/'))+'" onclick="App.toggleSub(this,\''+it.path+'\')"><span class="ico">'+it.icon+'</span><span class="lbl">'+it.label+'</span><span class="sub-arrow">▶</span></div>'
               + '<div class="submenu" id="sub_'+it.id+'">'+subs+'</div>';
        }
        return '<div class="menu-item" data-path="'+it.path+'" data-prefix="'+it.path+'" onclick="App.go(\''+it.path+'\')"><span class="ico">'+it.icon+'</span><span class="lbl">'+it.label+'</span></div>';
      }).join('');
      return '<div class="menu-group-title">'+grp.group+'</div>'+items;
    }).join('');

    document.getElementById('app').innerHTML =
      '<div class="layout">'
      +'<div class="sidebar" id="sidebar">'
      +  '<div class="logo" onclick="App.go(\'#/dashboard\')"><div class="logo-mark">D</div><div class="logo-text">Datara<small>DATA GOVERNANCE</small></div></div>'
      +  '<div class="menu">'+menuHtml+'</div>'
      +'</div>'
      +'<div class="main-area">'
      +  '<div class="topbar">'
      +    '<button class="collapse-btn" onclick="App.toggleSide()">☰</button>'
      +    '<div class="crumb" id="crumb"></div>'
      +    '<div class="top-search"><span class="s-ico">⌕</span><input id="g-search" placeholder="全局搜索：表 / 指标 / 任务 / 数据源" onkeydown="App.gSearch(event)"><span class="s-kbd">↵</span></div>'
      +    '<div class="env-switch" id="env-switch">'
      +      '<span data-env="dev" onclick="App.setEnv(\'dev\')">DEV</span>'
      +      '<span data-env="staging" onclick="App.setEnv(\'staging\')">STAGING</span>'
      +      '<span data-env="prod" onclick="App.setEnv(\'prod\')">PROD</span>'
      +    '</div>'
      +    '<div class="topbar-ico" title="通知" onclick="App.toggleNotif(event)">🔔<i class="dot"></i></div>'
      +    '<div class="avatar" onclick="App.toggleUser(event)" title="'+DB.user.name+'">'+DB.user.name.charAt(0)+'</div>'
      +  '</div>'
      +  '<div class="content" id="page-root"></div>'
      +'</div></div>'
      +'<div id="toast-root"></div>';
    this.setEnv(DB.env);
  },

  toggleSide: function(){ document.getElementById('sidebar').classList.toggle('collapsed'); },
  toggleSub: function(el, path){
    var wasOpen = el.classList.contains('open');
    document.querySelectorAll('.submenu').forEach(function(s){ s.classList.remove('expanded'); });
    document.querySelectorAll('.has-sub').forEach(function(s){ s.classList.remove('open'); });
    if(!wasOpen){
      el.classList.add('open');
      if(el.nextElementSibling) el.nextElementSibling.classList.add('expanded');
    }
    if(path) App.go(path);
  },
  setEnv: function(env){
    DB.env = env;
    document.querySelectorAll('#env-switch span').forEach(function(s){ s.classList.toggle('on', s.getAttribute('data-env')===env); });
    var e = {dev:'开发环境', staging:'联调环境', prod:'生产环境'}[env];
    UI.toast('已切换至 '+env.toUpperCase()+' · '+e, 'info');
  },
  gSearch: function(e){
    if(e.key === 'Enter'){
      var q = document.getElementById('g-search').value.trim();
      if(q) App.go('#/search?q='+encodeURIComponent(q));
    }
  },
  toggleNotif: function(e){
    e.stopPropagation();
    var old = document.getElementById('notif-panel');
    App.closePanels();
    if(old) return;
    var items = DB.notifications.map(function(n){
      return '<div class="np-item"><span style="font-size:15px">'+n.icon+'</span><div style="flex:1"><div class="np-title">'+n.title+'</div><div>'+n.desc+'</div><div class="np-time">'+n.time+'</div></div></div>';
    }).join('');
    var p = document.createElement('div');
    p.id='notif-panel'; p.className='notif-panel';
    p.innerHTML = '<div class="np-head"><span>通知中心</span><a style="font-size:12px" onclick="App.readAllNotif()">全部已读</a></div>'+items;
    document.body.appendChild(p);
  },
  readAllNotif: function(){ DB.notifications = []; App.closePanels(); UI.toast('通知已全部标记为已读', 'success'); document.querySelector('.topbar-ico .dot') && (document.querySelector('.topbar-ico .dot').style.display='none'); },
  toggleUser: function(e){
    e.stopPropagation();
    var old = document.getElementById('user-panel');
    App.closePanels();
    if(old) return;
    var p = document.createElement('div');
    p.id='user-panel'; p.className='user-panel';
    p.innerHTML = '<div style="padding:12px 15px;border-bottom:1px solid var(--border)"><b>'+DB.user.name+'</b><div style="color:var(--text-3);font-size:11.5px">'+DB.user.role+'</div></div>'
      +'<div class="up-item" onclick="UI.toast(\'原型演示：个人设置\',\'info\');App.closePanels()">⚙ 个人设置</div>'
      +'<div class="up-item" onclick="UI.toast(\'原型演示：切换语言\',\'info\');App.closePanels()">🌐 切换语言</div>'
      +'<div class="up-item danger" onclick="UI.toast(\'已退出登录（演示）\',\'success\');App.closePanels()">⏻ 退出登录</div>';
    document.body.appendChild(p);
  },
  closePanels: function(){
    var n = document.getElementById('notif-panel'); if(n) n.remove();
    var u = document.getElementById('user-panel'); if(u) u.remove();
  }
};
document.addEventListener('click', function(){ App.closePanels(); });

/* 页面动作挂载点：页面模块直接 A.xxx = fn，模板里 onclick="A.xxx(...)" */
var A = {};
window.A = A;

/* ============================================================
   UI 组件库
   ============================================================ */
var UI = {};
window.UI = UI;

UI.esc = function(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };

/* ---- 页头 ---- */
UI.pageHead = function(title, desc, acts, help){
  var helpHtml = '';
  if(help) helpHtml = '<span class="ph-help" onclick="UI.showHelp(this)" data-help="'+UI.esc(help)+'" title="操作指引">?</span>';
  return '<div class="page-head"><div class="ph-l"><h2>'+title+helpHtml+'</h2>'+(desc?'<div class="ph-desc">'+desc+'</div>':'')+'</div><div class="ph-acts">'+(acts||'')+'</div></div>';
};
/* 页面操作指引气泡 */
UI.showHelp = function(el){
  var old = document.getElementById('phHelpPop');
  if(old){ old.remove(); return; }
  var pop = document.createElement('div');
  pop.id = 'phHelpPop';
  pop.style.cssText = 'position:absolute;z-index:60;max-width:340px;background:#0d1b2e;color:#dbe4f3;border-radius:9px;padding:11px 14px;font-size:12px;line-height:1.7;box-shadow:0 8px 26px rgba(2,8,20,.35);white-space:pre-wrap';
  pop.textContent = el.getAttribute('data-help');
  document.body.appendChild(pop);
  var r = el.getBoundingClientRect();
  pop.style.left = Math.max(12, Math.min(r.left-40, window.innerWidth-360))+'px';
  pop.style.top = (r.bottom+8)+'px';
  var closer = function(ev){ if(!pop.contains(ev.target) && ev.target!==el){ pop.remove(); document.removeEventListener('click', closer); } };
  setTimeout(function(){ document.addEventListener('click', closer); }, 0);
};
/* 状态流转图：横向状态机展示，cur 为当前状态（列表页头部用） */
UI.stateFlow = function(steps, cur, note){
  var h = '<div class="stateflow">';
  steps.forEach(function(s, i){
    var on = s.k===cur;
    h += '<div class="sf-node'+(on?' on':'')+(s.done?' done':'')+'"><span class="sf-dot">'+(on?'◉':'○')+'</span><div><b>'+UI.esc(s.t)+'</b>'+(s.d?'<div class="sf-d">'+UI.esc(s.d)+'</div>':'')+'</div></div>';
    if(i<steps.length-1) h += '<div class="sf-line'+(steps[i+1].done||on?' hit':'')+'"></div>';
  });
  h += '</div>'+(note?'<div class="sf-note">'+UI.esc(note)+'</div>':'');
  return '<div class="card no-head stateflow-card"><div class="card-body">'+h+'</div></div>';
};

/* ---- 卡片 ---- */
UI.card = function(title, body, acts, extraHead){
  return '<div class="card"><div class="card-head"><h3>'+title+'</h3>'+(extraHead||'')+(acts?'<div class="ch-acts">'+acts+'</div>':'')+'</div><div class="card-body">'+body+'</div></div>';
};
UI.cardRaw = function(head, body){ return '<div class="card">'+head+'<div class="card-body">'+body+'</div></div>'; };

/* ---- toast ---- */
UI.toast = function(msg, type){
  var root = document.getElementById('toast-root');
  var t = document.createElement('div');
  t.className = 'toast '+(type||'success');
  var ico = {success:'✓', error:'✗', warn:'⚠', info:'ℹ'}[type||'success'];
  t.innerHTML = '<span class="t-ico">'+ico+'</span><span>'+msg+'</span>';
  root.appendChild(t);
  setTimeout(function(){ t.style.opacity='0'; t.style.transition='opacity .3s'; setTimeout(function(){t.remove();},300); }, 2400);
};

/* ---- 弹窗 ---- */
UI.modal = function(cfg){
  var root = document.getElementById('layer-root');
  var id = 'm'+Date.now();
  UI._modalOk = cfg.onOk || null;
  var foot = cfg.footer === false ? '' :
    '<div class="modal-foot">'+(cfg.footer || '<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn btn-primary" onclick="UI.okModal(\''+id+'\')">确定</button>')+'</div>';
  var mask = document.createElement('div');
  mask.className = 'modal-mask'; mask.id = 'mask_'+id; mask.onclick = function(e){ if(e.target===mask) UI.closeModal(); };
  mask.innerHTML = '<div class="modal '+(cfg.w||'')+'" id="'+id+'">'
    +'<div class="modal-head"><h3>'+cfg.title+'</h3><button class="modal-close" onclick="UI.closeModal()">✕</button></div>'
    +'<div class="modal-body">'+cfg.body+'</div>'+foot+'</div>';
  root.appendChild(mask);
  if(cfg.onMount) setTimeout(function(){ cfg.onMount(id); }, 0);
  return id;
};
UI.closeModal = function(){ var m = document.querySelector('.modal-mask'); if(m) m.remove(); UI._modalOk = null; };
UI.okModal = function(id){ if(UI._modalOk){ if(UI._modalOk(id) !== false) UI.closeModal(); } else UI.closeModal(); };

/* ---- 确认框 ---- */
UI.confirm = function(cfg){
  UI._cfOk = cfg.onOk;
  UI.modal({ title:cfg.title||'操作确认', w:'w-sm', footer:
    '<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn '+(cfg.danger?'btn-danger':'btn-primary')+'" onclick="UI.runConfirm()">确定</button>',
    body: '<div style="display:flex"><div class="ci" style="background:var(--'+(cfg.danger?'danger-bg':'info-bg')+')">'+(cfg.danger?'🗑':'❓')+'</div><div style="flex:1;padding-top:4px"><b>'+(cfg.msg||'确认执行该操作？')+'</b>'+(cfg.detail?'<div style="color:var(--text-3);font-size:12px;margin-top:5px">'+cfg.detail+'</div>':'')+'</div></div>' });
};
UI.runConfirm = function(){ var f = UI._cfOk; UI.closeModal(); if(f) f(); };

/* ---- 抽屉 ---- */
UI.drawer = function(cfg){
  var root = document.getElementById('layer-root');
  var wrap = document.createElement('div');
  wrap.innerHTML = '<div class="drawer-mask" onclick="UI.closeDrawer()"></div><div class="drawer '+(cfg.w||'')+'">'
    +'<div class="modal-head"><h3>'+cfg.title+'</h3><button class="modal-close" onclick="UI.closeDrawer()">✕</button></div>'
    +'<div class="modal-body">'+cfg.body+'</div>'
    +(cfg.footer===false?'':'<div class="modal-foot">'+(cfg.footer||'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="UI.okDrawer()">确定</button>')+'</div>')
    +'</div>';
  UI._drawerOk = cfg.onOk || null;
  root.appendChild(wrap);
  if(cfg.onMount) setTimeout(function(){ cfg.onMount(); }, 0);
};
UI.closeDrawer = function(){ var d = document.querySelector('.drawer'); if(d) d.parentNode.remove(); UI._drawerOk = null; };
UI.okDrawer = function(){ var f = UI._drawerOk; if(f){ if(f() !== false) UI.closeDrawer(); } else UI.closeDrawer(); };

/* ---- 表单 ---- */
UI.fInput = function(label, id, o){
  o = o||{};
  return '<div class="form-item'+(o.full?' full':'')+'"><div class="f-label">'+label+(o.req?'<span class="req">*</span>':'')+'</div>'
    +'<input class="inp" id="'+id+'" type="'+(o.type||'text')+'" value="'+UI.esc(o.value==null?'':o.value)+'" placeholder="'+(o.ph||'')+'" '+(o.readonly?'readonly':'')+(o.disabled?' disabled':'')+'>'
    +(o.help?'<div class="f-help">'+o.help+'</div>':'')+'</div>';
};
UI.fSelect = function(label, id, options, o){
  o = o||{};
  var opts = options.map(function(x){
    var v = typeof x==='object'? x.v : x, t = typeof x==='object'? x.t : x;
    return '<option value="'+UI.esc(v)+'" '+(String(v)===String(o.value)?'selected':'')+'>'+UI.esc(t)+'</option>';
  }).join('');
  return '<div class="form-item'+(o.full?' full':'')+'"><div class="f-label">'+label+(o.req?'<span class="req">*</span>':'')+'</div>'
    +'<select class="sel" id="'+id+'" '+(o.disabled?'disabled':'')+' '+(o.onchange?'onchange="'+o.onchange+'"':'')+'>'+opts+'</select>'
    +(o.help?'<div class="f-help">'+o.help+'</div>':'')+'</div>';
};
UI.fTextarea = function(label, id, o){
  o = o||{};
  return '<div class="form-item'+(o.full?' full':'')+'"><div class="f-label">'+label+(o.req?'<span class="req">*</span>':'')+'</div>'
    +'<textarea class="txa" id="'+id+'" rows="'+(o.rows||4)+'" placeholder="'+(o.ph||'')+'" '+(o.readonly?'readonly':'')+' '+(o.mono?'style="font-family:Consolas,monospace"':'')+'>'+UI.esc(o.value==null?'':o.value)+'</textarea>'
    +(o.help?'<div class="f-help">'+o.help+'</div>':'')+'</div>';
};
UI.fSwitch = function(label, id, on, help){
  return '<div class="form-item"><div class="f-label">'+label+'</div><div class="switch-row"><span class="switch'+(on?' on':'')+'" id="'+id+'" onclick="this.classList.toggle(\'on\')"></span>'+(help?'<span class="f-help" style="margin:0">'+help+'</span>':'')+'</div></div>';
};
UI.fRadio = function(label, id, options, value, help){
  return '<div class="form-item"><div class="f-label">'+label+'</div><div class="radio-group">'
    + options.map(function(x){ return '<label><input type="radio" name="'+id+'" value="'+UI.esc(x.v)+'" '+(String(x.v)===String(value)?'checked':'')+' onchange="UI._radioChange(\''+id+'\',this)">'+x.t+'</label>'; }).join('')
    + '</div>'+(help?'<div class="f-help">'+help+'</div>':'')+'</div>';
};
UI._radioChange = function(id, el){ UI['_rv_'+id] = el.value; if(UI['_rc_'+id]) UI['_rc_'+id](el.value); };
UI.fCheckGroup = function(label, id, options, values, help){
  values = values||[];
  return '<div class="form-item"><div class="f-label">'+label+'</div><div class="check-group">'
    + options.map(function(x){ return '<label><input type="checkbox" class="ck-'+id+'" value="'+UI.esc(x.v)+'" '+(values.indexOf(x.v)>=0?'checked':'')+'>'+x.t+'</label>'; }).join('')
    + '</div>'+(help?'<div class="f-help">'+help+'</div>':'')+'</div>';
};
UI.val = function(id){ var el = document.getElementById(id); return el? (el.type==='checkbox'? el.checked : el.value.trim()) : ''; };
UI.radioVal = function(id, def){ return UI['_rv_'+id] !== undefined ? UI['_rv_'+id] : def; };
UI.checkVals = function(cls){ return Array.prototype.map.call(document.querySelectorAll('.'+cls+':checked'), function(e){return e.value;}); };
UI.switchOn = function(id){ var el = document.getElementById(id); return el? el.classList.contains('on') : false; };

/* ---- 步骤条 ---- */
UI.steps = function(steps, cur){
  var out = '<div class="steps">';
  steps.forEach(function(s, i){
    var cls = i < cur ? 'done' : (i === cur ? 'active' : '');
    out += '<div class="step '+cls+'"><div class="s-num">'+(i<cur?'✓':(i+1))+'</div><div class="s-txt">'+s+'</div></div>';
    if(i < steps.length-1) out += '<div class="step-line '+(i<cur?'done':'')+'"></div>';
  });
  return out+'</div>';
};

/* ---- Tabs ---- */
UI.tabs = function(id, tabs, active, onchange){
  return '<div class="tabs" id="'+id+'">'+tabs.map(function(t, i){
    return '<div class="tab'+(i===active?' on':'')+'" data-idx="'+i+'" onclick="UI.switchTab(\''+id+'\','+i+','+(onchange?'1':'0')+','+(t.render? '1':'0')+')">'+t.label+(t.cnt!=null?'<span class="cnt">'+t.cnt+'</span>':'')+'</div>';
  }).join('')+'</div>';
};
UI.switchTab = function(id, idx, hasChange, hasRender){
  var tabs = document.querySelectorAll('#'+id+' .tab');
  tabs.forEach(function(t){ t.classList.remove('on'); });
  tabs[idx].classList.add('on');
  var cb = UI._tabCb[id];
  if(cb) cb(idx);
};
UI._tabCb = {};

/* ---- 时间线 ---- */
UI.timeline = function(items){
  return '<div class="timeline">'+items.map(function(it){
    return '<div class="tl-item '+(it.cls||'')+'"><div style="display:flex;justify-content:space-between;gap:10px"><b style="font-size:12.5px">'+it.title+'</b>'+(it.time?'<span class="tl-time">'+it.time+'</span>':'')+'</div><div class="tl-body">'+(it.body||'')+'</div></div>';
  }).join('')+'</div>';
};

/* ---- 描述列表 ---- */
UI.desc = function(items){
  return '<div class="desc-grid">'+items.map(function(it){
    return '<div class="desc-item"><span class="d-k">'+it[0]+'</span><span class="d-v">'+(it[1]==null||it[1]===''?'-':it[1])+'</span></div>';
  }).join('')+'</div>';
};
UI.kv = function(items){
  return items.map(function(it){ return '<div class="kv-row"><span class="k">'+it[0]+'</span><span class="v">'+(it[1]==null||it[1]===''?'-':it[1])+'</span></div>'; }).join('');
};

/* ---- 树 ---- */
UI.tree = function(id, nodes){
  /* nodes: [{label, icon, data:{...}, children:[...]}]  动作由页面在渲染后绑定或使用onclick字符串 */
  function r(list, lv){
    return list.map(function(n){
      var hasKids = n.children && n.children.length;
      return '<div class="t-node'+(n.on?' on':'')+'" '+(n.attrs||'')+'><span class="caret'+(hasKids?' open':'')+'">▶</span><span class="t-ico">'+(n.icon||'▤')+'</span><span>'+UI.esc(n.label)+'</span></div>'
        + (hasKids? '<div class="t-children">'+r(n.children, lv+1)+'</div>' : '');
    }).join('');
  }
  return '<div class="tree" id="'+id+'">'+r(nodes, 0)+'</div>';
};

/* ============================================================
   通用数据表格（搜索/筛选/排序/分页/多选/操作列）
   ============================================================ */
UI._tblCfg = {};
UI._tblState = {};

UI.tbl = function(cfg){
  UI._tblCfg[cfg.id] = cfg;
  UI._tblState[cfg.id] = UI._tblState[cfg.id] || {page:1, q:'', filters:{}, sortK:'', dir:1, sel:[]};
  return '<div id="tblw_'+cfg.id+'">'+UI.renderTbl(cfg.id)+'</div>';
};

UI.renderTbl = function(id){
  var cfg = UI._tblCfg[id], st0 = UI._tblState[id];
  var data = cfg.data();
  /* 搜索 */
  if(st0.q){
    var q = st0.q.toLowerCase();
    data = data.filter(function(row){
      return (cfg.searchKeys||Object.keys(row)).some(function(k){
        return String(row[k]==null?'':row[k]).toLowerCase().indexOf(q) >= 0;
      });
    });
  }
  /* 筛选 */
  (cfg.filters||[]).forEach(function(f){
    var v = st0.filters[f.k];
    if(v && v !== '__all') data = data.filter(function(row){ return String(row[f.k]) === v; });
  });
  /* 排序 */
  if(st0.sortK){
    var k = st0.sortK, d = st0.dir;
    data = data.slice().sort(function(a,b){ return String(a[k]).localeCompare(String(b[k]), 'zh-CN') * d; });
  }
  var total = data.length, pages = Math.max(1, Math.ceil(total / cfg.pageSize)), page = Math.min(st0.page, pages);
  st0.page = page;
  var rows = data.slice((page-1)*cfg.pageSize, page*cfg.pageSize);

  var html = '<div class="toolbar">';
  html += '<span class="search-input"><span class="si">⌕</span><input placeholder="'+(cfg.searchPh||'输入关键词搜索')+'" value="'+UI.esc(st0.q)+'" oninput="UI._tq(\''+id+'\',this.value)"></span>';
  (cfg.filters||[]).forEach(function(f){
    html += '<select class="sel" style="width:auto" onchange="UI._tf(\''+id+'\',\''+f.k+'\',this.value)">'
      +'<option value="__all">全部'+(f.label?' '+f.label:'')+'</option>'
      + f.options.map(function(o){ return '<option value="'+UI.esc(o.v)+'" '+(String(st0.filters[f.k])===String(o.v)?'selected':'')+'>'+UI.esc(o.t)+'</option>'; }).join('')+'</select>';
  });
  html += '<span class="spacer"></span>';
  if(cfg.toolbarActs) html += cfg.toolbarActs();
  html += '</div>';

  html += '<div class="table-wrap"><table class="tbl"><thead><tr>';
  if(cfg.selectable) html += '<th style="width:34px"><input type="checkbox" class="row-check" '+(st0.sel.length && st0.sel.length===rows.length?'checked':'')+' onchange="UI._tselAll(\''+id+'\',this.checked)"></th>';
  cfg.cols.forEach(function(c){
    if(c.sortable) html += '<th class="sortable" onclick="UI._tsort(\''+id+'\',\''+c.k+'\')">'+c.t+(st0.sortK===c.k?(st0.dir>0?' ↑':' ↓'):' ⇅')+'</th>';
    else html += '<th style="'+(c.w?'width:'+c.w:'')+'">'+c.t+'</th>';
  });
  if(cfg.ops) html += '<th style="width:'+(cfg.opsW||180)+'">操作</th>';
  html += '</tr></thead><tbody>';
  if(!rows.length){
    html += '<tr><td colspan="'+(cfg.cols.length+1+(cfg.selectable?1:0))+'"><div class="tbl-empty"><span class="ico">⌀</span>暂无数据</div></td></tr>';
  }
  rows.forEach(function(row){
    html += '<tr'+(cfg.rowClick?' class="link-row" onclick="UI._rowClick(\''+id+'\',\''+row[cfg.rowKey]+'\')"':'')+'>';
    if(cfg.selectable) html += '<td><input type="checkbox" class="row-check" '+(st0.sel.indexOf(String(row[cfg.rowKey]))>=0?'checked':'')+' onclick="event.stopPropagation();UI._tsel(\''+id+'\',\''+row[cfg.rowKey]+'\',this.checked)"></td>';
    cfg.cols.forEach(function(c){
      html += '<td>'+(c.render? c.render(row) : UI.esc(row[c.k]))+'</td>';
    });
    if(cfg.ops) html += '<td onclick="event.stopPropagation()"><div class="td-acts">'+cfg.ops(row)+'</div></td>';
    html += '</tr>';
  });
  html += '</tbody></table></div>';

  html += '<div class="pager"><span>共 '+total+' 条</span><span style="margin-left:8px">每页 '+cfg.pageSize+' 条</span>'
    +'<span class="pg" onclick="UI._tp(\''+id+'\',1)">«</span>'
    +'<span class="pg" onclick="UI._tp(\''+id+'\','+(page-1)+')">‹</span>';
  for(var i=1;i<=pages;i++){ if(pages>7 && i>2 && i<pages-1 && Math.abs(i-page)>1) continue; html += '<span class="pg'+(i===page?' on':'')+'" onclick="UI._tp(\''+id+'\','+i+')">'+i+'</span>'; }
  html += '<span class="pg" onclick="UI._tp(\''+id+'\','+(page+1)+')">›</span>'
    +'<span class="pg" onclick="UI._tp(\''+id+'\','+pages+')">»</span></div>';

  return html;
};

/* 交互后的局部刷新：容器已插入 DOM 时才更新 */
UI._refreshTbl = function(id){
  var el = document.getElementById('tblw_'+id);
  if(el) el.innerHTML = UI.renderTbl(id);
};

UI._tq = function(id, v){ var s = UI._tblState[id]; s.q = v; s.page = 1; UI._refreshTbl(id); };
UI._tf = function(id, k, v){ var s = UI._tblState[id]; s.filters[k] = v; s.page = 1; UI._refreshTbl(id); };
UI._tsort = function(id, k){ var s = UI._tblState[id]; if(s.sortK===k) s.dir = -s.dir; else { s.sortK = k; s.dir = 1; } UI._refreshTbl(id); };
UI._tp = function(id, p){ var s = UI._tblState[id]; s.page = p; UI._refreshTbl(id); };
UI._tsel = function(id, key, on){ var s = UI._tblState[id]; var i = s.sel.indexOf(String(key)); if(on && i<0) s.sel.push(String(key)); if(!on && i>=0) s.sel.splice(i,1); };
UI._tselAll = function(id, on){ var s = UI._tblState[id]; s.sel = []; if(on){ var cfg=UI._tblCfg[id]; var data=cfg.data(); data.forEach(function(r){ s.sel.push(String(r[cfg.rowKey])); }); } UI._refreshTbl(id); };
UI._rowClick = function(id, key){ var cfg = UI._tblCfg[id]; if(cfg.rowClick) cfg.rowClick(key); };
UI.selRows = function(id){ return (UI._tblState[id]||{sel:[]}).sel; };

/* ============================================================
   SVG 轻量图表
   ============================================================ */
var Charts = {};
window.Charts = Charts;

Charts.line = function(cfg){
  var w = cfg.w||560, h = cfg.h||240, pl = 42, pr = 14, pt = 16, pb = 26;
  var labels = cfg.labels, series = cfg.series;
  var all = []; series.forEach(function(s){ all = all.concat(s.data); });
  var max = Math.max.apply(null, all) * 1.1, min = 0;
  var iw = w-pl-pr, ih = h-pt-pb;
  function X(i){ return pl + iw * (labels.length===1?0.5:(i/(labels.length-1))); }
  function Y(v){ return pt + ih * (1 - (v-min)/(max-min||1)); }
  var svg = '<svg width="100%" viewBox="0 0 '+w+' '+h+'" style="display:block">';
  for(var g=0; g<=4; g++){
    var gy = pt + ih*g/4;
    svg += '<line x1="'+pl+'" y1="'+gy+'" x2="'+(w-pr)+'" y2="'+gy+'" stroke="#eef1f6" stroke-width="1"/>';
    svg += '<text x="'+(pl-6)+'" y="'+(gy+4)+'" font-size="10" fill="#8c94a6" text-anchor="end">'+(Math.round((max-min)*(4-g)/4*10)/10)+'</text>';
  }
  labels.forEach(function(lb, i){ svg += '<text x="'+X(i)+'" y="'+(h-8)+'" font-size="10" fill="#8c94a6" text-anchor="middle">'+lb+'</text>'; });
  series.forEach(function(s){
    var pts = s.data.map(function(v,i){ return X(i)+','+Y(v); }).join(' ');
    svg += '<polyline points="'+pts+'" fill="none" stroke="'+s.color+'" stroke-width="2" stroke-linejoin="round"/>';
    s.data.forEach(function(v,i){ svg += '<circle cx="'+X(i)+'" cy="'+Y(v)+'" r="3" fill="#fff" stroke="'+s.color+'" stroke-width="1.8"/>'; });
  });
  svg += '</svg>';
  return svg;
};

Charts.bars = function(cfg){
  var w = cfg.w||560, h = cfg.h||240, pl = 42, pr = 14, pt = 16, pb = 26;
  var labels = cfg.labels, series = cfg.series;
  var all = []; series.forEach(function(s){ all = all.concat(s.data); });
  var max = Math.max.apply(null, all) * 1.15;
  var iw = w-pl-pr, ih = h-pt-pb;
  var bw = iw/labels.length, gap = bw*0.18;
  var bwr = (bw-gap*2)/series.length;
  var svg = '<svg width="100%" viewBox="0 0 '+w+' '+h+'" style="display:block">';
  for(var g=0; g<=4; g++){
    var gy = pt + ih*g/4;
    svg += '<line x1="'+pl+'" y1="'+gy+'" x2="'+(w-pr)+'" y2="'+gy+'" stroke="#eef1f6"/>';
    svg += '<text x="'+(pl-6)+'" y="'+(gy+4)+'" font-size="10" fill="#8c94a6" text-anchor="end">'+Math.round(max*(4-g)/4)+'</text>';
  }
  labels.forEach(function(lb, i){
    svg += '<text x="'+(pl+bw*i+bw/2)+'" y="'+(h-8)+'" font-size="10" fill="#8c94a6" text-anchor="middle">'+lb+'</text>';
    series.forEach(function(s, si){
      var v = s.data[i], bh = ih*v/max;
      svg += '<rect x="'+(pl+bw*i+gap+bwr*si)+'" y="'+(pt+ih-bh)+'" width="'+(bwr-3)+'" height="'+bh+'" rx="3" fill="'+s.color+'"><title>'+lb+' '+s.name+' '+v+'</title></rect>';
    });
  });
  svg += '</svg>';
  return svg;
};

Charts.donut = function(cfg){
  var size = cfg.size||170, r = size/2-8, cx = size/2, cy = size/2;
  var total = 0; cfg.items.forEach(function(i){ total += i.value; });
  var ang = -90, svg = '<svg width="100%" viewBox="0 0 '+size+' '+size+'" style="max-width:'+size+'px;margin:0 auto;display:block">';
  cfg.items.forEach(function(it){
    var a = total? it.value/total*360 : 0;
    var a2 = ang + a;
    if(a >= 359.9){
      svg += '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="'+it.color+'" stroke-width="18"/>';
    } else {
      var x1 = cx + r*Math.cos(ang*Math.PI/180), y1 = cy + r*Math.sin(ang*Math.PI/180);
      var x2 = cx + r*Math.cos(a2*Math.PI/180), y2 = cy + r*Math.sin(a2*Math.PI/180);
      svg += '<path d="M '+x1+' '+y1+' A '+r+' '+r+' 0 '+(a>180?1:0)+' 1 '+x2+' '+y2+'" fill="none" stroke="'+it.color+'" stroke-width="18" stroke-linecap="butt"><title>'+it.name+' '+it.value+'</title></path>';
    }
    ang = a2;
  });
  svg += '<text x="'+cx+'" y="'+(cy-4)+'" font-size="22" font-weight="700" fill="#242938" text-anchor="middle">'+(cfg.center||total)+'</text>';
  svg += '<text x="'+cx+'" y="'+(cy+16)+'" font-size="10" fill="#8c94a6" text-anchor="middle">'+(cfg.centerLabel||'合计')+'</text>';
  svg += '</svg>';
  return svg;
};

Charts.ring = function(percent, size, color, label){
  size = size||90; var r = size/2-7, c = 2*Math.PI*r, cx=size/2, cy=size/2;
  color = color || (percent>=90?'#16a34a':percent>=75?'#1668dc':percent>=60?'#d97706':'#e5484d');
  return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+'">'
    +'<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="#edf0f5" stroke-width="8"/>'
    +'<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="'+color+'" stroke-width="8" stroke-linecap="round" stroke-dasharray="'+(c*percent/100)+' '+c+'" transform="rotate(-90 '+cx+' '+cy+')"/>'
    +'<text x="'+cx+'" y="'+(cy+5)+'" font-size="15" font-weight="700" fill="#242938" text-anchor="middle">'+percent+'</text></svg>'
    +(label?'<div style="text-align:center;font-size:11px;color:var(--text-3);margin-top:2px">'+label+'</div>':'');
};

Charts.hbars = function(items){ /* items:[{name, value, max, color}] */
  var max = Math.max.apply(null, items.map(function(i){return i.value;}));
  return '<div>'+items.map(function(it){
    var pct = Math.round(it.value/(it.max||max)*100);
    return '<div style="display:flex;align-items:center;gap:10px;margin-bottom:9px;font-size:12px">'
      +'<span style="width:76px;color:var(--text-2);text-align:right;flex-shrink:0">'+it.name+'</span>'
      +'<div class="progress" style="flex:1"><div class="bar" style="width:'+pct+'%;background:'+(it.color||'linear-gradient(90deg,#1668dc,#4d9aff)')+'"></div></div>'
      +'<span style="width:56px;font-weight:600">'+it.value+(it.suffix||'')+'</span></div>';
  }).join('')+'</div>';
};

/* ============================================================
   通用业务动作
   ============================================================ */
/* 新建/编辑弹窗表单通用保存 */
UI._editTarget = null;
A._noop = function(){};

/* 通用删除 */
UI.delRow = function(list, key, id, name, after){
  UI.confirm({ title:'删除确认', danger:true, msg:'确认删除「'+name+'」吗？', detail:'删除后不可恢复，如被其他资源引用将无法删除。', onOk:function(){
    var i = list.findIndex(function(x){ return String(x[key])===String(id); });
    if(i>=0){ list.splice(i,1); UI.toast('已删除「'+name+'」', 'success'); if(after) after(); App.resolve(); }
  }});
};

/* 通用启停切换 */
UI.toggleStatus = function(obj, after){
  if(obj.status === 'enabled' || obj.status === 'published' || obj.status === 'online'){
    obj.status = 'disabled';
    UI.toast('「'+(obj.name||obj.id)+'」已停用/下线', 'info');
  } else {
    obj.status = obj._onStatus || 'enabled';
    UI.toast('「'+(obj.name||obj.id)+'」已启用/上线', 'success');
  }
  if(after) after();
  App.resolve();
};

/* 下载文本文件 */
UI.download = function(filename, content, mime){
  var blob = new Blob([content], {type: mime||'text/plain;charset=utf-8'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.appendChild(a); a.click();
  setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 100);
  UI.toast('已生成并下载「'+filename+'」', 'success');
};
