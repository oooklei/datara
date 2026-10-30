/* ============================================================
   VC 可视化画布引擎（共享组件 · DolphinScheduler 风格）
   - 左侧元件面板（分组、可拖拽入画布）
   - 中间画布：HTML 节点 + SVG 连线（顺序线/分支线/依赖线）
   - 节点：点击选中→onNodeClick(右侧编辑)、hover→摘要 tooltip、右键删除
   - 连线：节点悬停出现连接点，点源节点连接点再点目标节点完成连线
   - 自动布局（拓扑分层）、缩放、校验（环/孤立/断链）
   - mark/highlight：供质量标记、血缘定位等场景复用
   ============================================================ */
var VC = (function(){
  var G = {};                 /* id -> instance */
  var seq = 0;

  var KIND_STYLE = {
    flow:   {stroke:'#7aa2f7', dash:'',      end:'arrow'},
    branch: {stroke:'#f59e0b', dash:'7 5',   end:'diamond'},
    dep:    {stroke:'#94a3b8', dash:'2 5',   end:'arrow'}
  };
  var STATUS_DOT = {success:'#16a34a', running:'#1668dc', error:'#e5484d', idle:'#94a3b8', warn:'#f59e0b'};

  /* ---------- 数据工具 ---------- */
  function topoLevels(nodes, edges){
    var indeg = {}, out = {}, map = {};
    nodes.forEach(function(n){ map[n.id]=n; indeg[n.id]=0; out[n.id]=[]; });
    edges.forEach(function(e){ if(map[e.from]&&map[e.to]){ out[e.from].push(e.to); indeg[e.to]=(indeg[e.to]||0)+1; }});
    var lv = {}, q = nodes.filter(function(n){return !indeg[n.id];}).map(function(n){return n.id;});
    q.forEach(function(id){ lv[id]=0; });
    while(q.length){
      var cur = q.shift();
      out[cur].forEach(function(t){ if(lv[t]==null||lv[t]<lv[cur]+1) lv[t]=lv[cur]+1; indeg[t]--; if(indeg[t]===0) q.push(t); });
    }
    nodes.forEach(function(n){ if(lv[n.id]==null) lv[n.id]=0; });
    return lv;
  }

  function el(id){ return document.getElementById(id); }

  /* ---------- 实例 ---------- */
  function create(cfg){
    var uid = 'vc'+(++seq);
    var inst = {
      uid: uid, cfg: cfg,
      nodes: cfg.nodes||[], edges: cfg.edges||[],
      sel: null, drag: null, linkFrom: null, scale: 1,
      mode: cfg.mode || (cfg.editable? 'edit':'view')
    };
    G[uid] = inst;

    var root = typeof cfg.mount==='string'? el(cfg.mount.replace('#','')) : cfg.mount;
    root.innerHTML =
      '<div class="vc-root" id="'+uid+'">'
      + (cfg.legend!==false? vcLegend(cfg, inst.mode):'')
      + '<div class="vc-body"'+(cfg.height? ' style="height:'+cfg.height+'px"':'')+'>'
      +   (cfg.palette && inst.mode==='edit'? vcPalette(uid,cfg.palette):'')
      +   '<div class="vc-canvas" id="'+uid+'_canvas">'
      +     '<div class="vc-inner" id="'+uid+'_inner" style="transform-origin:0 0">'
      +       '<svg class="vc-svg" id="'+uid+'_svg"><defs>'
      +         '<marker id="'+uid+'_arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#7aa2f7"/></marker>'
      +         '<marker id="'+uid+'_arrowB" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 L3,5 z" fill="#f59e0b"/></marker>'
      +         '<marker id="'+uid+'_arrowD" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#94a3b8"/></marker>'
      +       '</defs></svg>'
      +       '<div class="vc-nodes" id="'+uid+'_nodes"></div>'
      +     '</div>'
      +     '<div class="vc-tools">'
      +       '<span class="vc-tool" title="放大" onclick="VC._zoom(\''+uid+'\',1.2)">＋</span>'
      +       '<span class="vc-tool" title="缩小" onclick="VC._zoom(\''+uid+'\',0.8)">－</span>'
      +       '<span class="vc-tool" title="适应画布" onclick="VC._zoom(\''+uid+'\',0)">▢</span>'
      +       (inst.mode==='edit'? '<span class="vc-tool" title="自动排版" onclick="VC.layout(\''+uid+'\')">⌗</span>'
      +       '<span class="vc-tool vc-danger" title="清空画布" onclick="VC._clear(\''+uid+'\')">🗑</span>':'')
      +     '</div>'
      +     '<div class="vc-tip" id="'+uid+'_tip"></div>'
      +     '<div class="vc-linkbar" id="'+uid+'_linkbar"></div>'
      +   '</div>'
      + '</div></div>';

    bindCanvas(uid);
    render(uid);
    return uid;
  }

  function vcLegend(cfg, mode){
    var items = '<span><span class="lg-dot" style="background:#7aa2f7"></span>顺序执行</span>'
      + '<span><span class="lg-dot" style="background:#f59e0b"></span>条件分支</span>'
      + '<span><span class="lg-dot" style="background:#94a3b8"></span>依赖（跨流）</span>';
    (cfg.legendExtra||[]).forEach(function(x){ items += '<span><span class="lg-dot" style="background:'+x.c+'"></span>'+x.t+'</span>'; });
    if(mode==='edit') items += '<span style="color:var(--text-3)">拖拽左侧元件入画布 · 点连接点再点目标节点连线 · 右键节点删除</span>';
    return '<div class="vc-legend">'+items+'</div>';
  }

  /* 左侧元件库：分类折叠 + 关键字过滤（低代码平台范式） */
  function vcPalette(uid, cats){
    var h = '<div class="vc-side" id="'+uid+'_side"><div class="vc-side-h">元件库'
      + '<input class="vc-side-q" placeholder="搜索元件…" oninput="VC._palFilter(\''+uid+'\',this.value)"></div>';
    cats.forEach(function(c, ci){
      h += '<div class="vc-cat-g" id="'+uid+'_catg'+ci+'">'
        + '<div class="vc-cat vc-cat-t" onclick="VC._palToggle(\''+uid+'\','+ci+')"><span>'+UI.esc(c.cat)+'</span>'
        + '<b class="vc-cat-n">'+c.items.length+'</b><i class="vc-cat-a">▾</i></div>';
      c.items.forEach(function(it){
        h += '<div class="vc-item" draggable="true" data-kw="'+UI.esc((it.name+' '+(it.desc||'')+' '+(it.summary||'')).toLowerCase())+'"'
          + ' title="'+UI.esc(it.summary||it.desc||it.name)+'"'
          + ' ondragstart="VC._dragStart(event,\''+uid+'\',\''+it.type+'\')">'
          + '<span class="vc-ico" style="background:'+it.color+'18;color:'+it.color+'">'+it.icon+'</span>'
          + '<div><b>'+it.name+'</b><div style="font-size:10px;color:var(--text-3)">'+(it.desc||'')+'</div></div></div>';
      });
      h += '</div>';
    });
    return h+'</div>';
  }

  /* ---------- 渲染 ---------- */
  function render(uid){
    var inst = G[uid]; if(!inst) return;
    renderNodes(uid); renderEdges(uid);
  }

  function nodeSize(n){
    if(n && n.big) return {w: 176, h: 64};
    return {w: 148, h: 46};
  }

  function renderNodes(uid){
    var inst = G[uid];
    var box = el(uid+'_nodes'); if(!box) return;
    var html = '';
    /* 泳道分层背景（拓扑图用） */
    (inst.cfg.bands||[]).forEach(function(b){
      html += '<div class="vc-band" style="top:'+b.y+'px;left:'+(b.x||0)+'px;width:'+(b.w||1520)+'px;'+(b.h? 'height:'+b.h+'px;':'')+'">'
        + '<span class="vc-band-lb">'+UI.esc(b.label)+'</span>'
        + (b.sub? '<span class="vc-band-sub">'+UI.esc(b.sub)+'</span>':'') + '</div>';
    });
    inst.nodes.forEach(function(n){
      var dot = n.status? '<span class="vc-dot" style="background:'+(STATUS_DOT[n.status]||'#94a3b8')+'"></span>':'';
      var mark = n.mark? '<span class="vc-mark '+(n.mark==='ok'?'vc-mark-ok':'vc-mark-err')+'">'+(n.mark==='ok'?'✓':'!')+'</span>':'';
      var sz = nodeSize(n);
      var inner = inst.cfg.nodeRender? inst.cfg.nodeRender(n)
        : '<div class="vc-node-main">'
        +   '<span class="vc-ico" style="background:'+(n.color||'#1668dc')+'18;color:'+(n.color||'#1668dc')+'">'+(n.icon||'▣')+'</span>'
        +   '<div class="vc-node-txt"><b title="'+UI.esc(n.name)+'">'+UI.esc(n.name)+'</b>'
        +   '<span class="vc-node-type">'+UI.esc(n.type)+(n.sub? ' · '+UI.esc(n.sub):'')+'</span></div>'
        +   dot + mark
        + '</div>';
      html += '<div class="vc-node'+(inst.sel===n.id?' sel':'')+(n.big?' vc-node-big':'')+'" id="'+uid+'_n_'+n.id+'" data-id="'+n.id+'"'
        + ' style="left:'+n.x+'px;top:'+n.y+'px;width:'+sz.w+'px;height:'+sz.h+'px;border-top:3px solid '+(n.color||'#1668dc')+'">'
        + inner
        + (inst.mode==='edit'? '<span class="vc-port" title="拖连到目标节点" onmousedown="VC._linkStart(event,\''+uid+'\',\''+n.id+'\')"></span>':'')
        + '</div>';
    });
    box.innerHTML = html;
    bindNodeEvents(uid);
  }

  function renderEdges(uid){
    var inst = G[uid];
    var svg = el(uid+'_svg'); if(!svg) return;
    var map = {}; inst.nodes.forEach(function(n){ map[n.id]=nodeSize(n); });
    var pos = {}; inst.nodes.forEach(function(n){ pos[n.id] = {x:n.x, y:n.y}; });
    var maxR = 0, maxB = 0;
    inst.nodes.forEach(function(n){ maxR = Math.max(maxR, n.x+map[n.id].w+120); maxB = Math.max(maxB, n.y+map[n.id].h+120); });
    svg.setAttribute('width', Math.max(maxR, 800)); svg.setAttribute('height', Math.max(maxB, 400));
    var h = '';
    inst.edges.forEach(function(e, i){
      var a = pos[e.from], b = pos[e.to]; if(!a||!b) return;
      var aw = map[e.from].w, ah = map[e.from].h, bw = map[e.to].w, bh = map[e.to].h;
      var x1 = a.x+aw, y1 = a.y+ah/2, x2 = b.x, y2 = b.y+bh/2;
      var mx = (x1+x2)/2;
      var st = KIND_STYLE[e.kind||'flow'];
      var active = e.run? ' vc-edge-run':'';
      h += '<path class="vc-edge'+active+'" data-i="'+i+'" d="M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2+'"'
        + ' style="stroke:'+st.stroke+(st.dash? ';stroke-dasharray:'+st.dash:'')+'"'
        + ' marker-end="url(#'+uid+(e.kind==='branch'?'_arrowB':e.kind==='dep'?'_arrowD':'_arrow')+')"/>';
      if(e.label){
        h += '<text class="vc-edge-label" x="'+((x1+x2)/2)+'" y="'+((y1+y2)/2-6)+'" text-anchor="middle">'+UI.esc(e.label)+'</text>';
      }
    });
    var old = svg.querySelectorAll('path.vc-edge, text.vc-edge-label');
    for(var i=old.length-1;i>=0;i--) old[i].remove();
    svg.insertAdjacentHTML('beforeend', h);
  }

  /* ---------- 交互绑定 ---------- */
  function bindCanvas(uid){
    var canvas = el(uid+'_canvas'); if(!canvas) return;
    canvas.addEventListener('dragover', function(ev){ ev.preventDefault(); });
    canvas.addEventListener('drop', function(ev){
      ev.preventDefault();
      var type = ev.dataTransfer.getData('text/vc-type');
      if(!type) return;
      var inst = G[uid];
      var meta = findPaletteItem(inst.cfg.palette, type) || {type:type, name:type, icon:'▣', color:'#1668dc'};
      var rect = el(uid+'_inner').getBoundingClientRect();
      var sc = inst.scale||1;
      var x = (ev.clientX - rect.left)/sc - 74, y = (ev.clientY - rect.top)/sc - 23;
      VC.addNode(uid, {id:'nd'+Date.now()%100000, name: meta.name, type: meta.type, icon: meta.icon, color: meta.color,
        x: Math.max(8,x), y: Math.max(8,y), cat: meta.cat, summary: meta.summary || (meta.name+'（'+meta.type+'）· 未配置'), cfg: {}});
    });
    canvas.addEventListener('mousemove', function(ev){ doDrag(uid, ev); });
    canvas.addEventListener('mouseup', function(){ endDrag(uid); });
  }

  function findPaletteItem(cats, type){
    if(!cats) return null;
    for(var i=0;i<cats.length;i++){ for(var j=0;j<cats[i].items.length;j++){ if(cats[i].items[j].type===type) return cats[i].items[j]; } }
    return null;
  }

  function bindNodeEvents(uid){
    var inst = G[uid];
    inst.nodes.forEach(function(n){
      var nd = el(uid+'_n_'+n.id); if(!nd) return;
      nd.addEventListener('mousedown', function(ev){
        if(ev.button!==0 || ev.target.classList.contains('vc-port')) return;
        if(inst.linkFrom){ finishLink(uid, n.id); return; }
        inst.sel = n.id; inst.drag = {id:n.id, sx:ev.clientX, sy:ev.clientY, ox:n.x, oy:n.y};
        nd.classList.add('sel');
        renderEdges(uid);
        ev.stopPropagation();
      });
      nd.addEventListener('click', function(ev){
        if(ev.target.classList.contains('vc-port')) return;
        if(inst._lastDownMoved) return;
        if(inst.cfg.onNodeClick) inst.cfg.onNodeClick(n, apiOf(uid));
      });
      nd.addEventListener('mouseenter', function(){
        if(!n.summary && !n.cfg) return;
        var tip = el(uid+'_tip');
        tip.innerHTML = vcTip(n);
        tip.style.display = 'block';
        var canvas = el(uid+'_canvas');
        tip.style.left = Math.min(n.x + 158, canvas.clientWidth - 300) + 'px';
        tip.style.top = Math.min(n.y + 8, canvas.clientHeight - 140) + 'px';
      });
      nd.addEventListener('mouseleave', function(){ var t = el(uid+'_tip'); if(t) t.style.display='none'; });
      nd.addEventListener('contextmenu', function(ev){
        ev.preventDefault();
        if(inst.mode!=='edit') return;
        if(inst.cfg.onNodeContext){ inst.cfg.onNodeContext(n, apiOf(uid)); return; }
        VC.delNode(uid, n.id);
        UI.toast('已删除节点：'+n.name, 'info');
      });
    });
  }

  function vcTip(n){
    var rows = '';
    if(n.summary) rows += '<div class="vc-tip-desc">'+UI.esc(n.summary)+'</div>';
    if(n.cfg){
      Object.keys(n.cfg).forEach(function(k){
        if(n.cfg[k]==null||n.cfg[k]==='') return;
        rows += '<div class="vc-tip-row"><span>'+UI.esc(k)+'</span><b>'+UI.esc(String(n.cfg[k]))+'</b></div>';
      });
    }
    if(n.inOut) rows += '<div class="vc-tip-row"><span>输入→输出</span><b>'+UI.esc(n.inOut)+'</b></div>';
    return '<div class="vc-tip-h"><span class="vc-ico" style="background:'+(n.color||'#1668dc')+'18;color:'+(n.color||'#1668dc')+'">'+(n.icon||'▣')+'</span><b>'+UI.esc(n.name)+'</b><span class="vc-tip-type">'+UI.esc(n.type)+'</span></div>'+rows;
  }

  function doDrag(uid, ev){
    var inst = G[uid]; if(!inst||!inst.drag) return;
    var sc = inst.scale||1;
    var n = inst.nodes.find(function(x){return x.id===inst.drag.id;});
    if(!n) return;
    inst._lastDownMoved = true;
    n.x = inst.drag.ox + (ev.clientX-inst.drag.sx)/sc;
    n.y = inst.drag.oy + (ev.clientY-inst.drag.sy)/sc;
    var nd = el(uid+'_n_'+n.id);
    if(nd){ nd.style.left = n.x+'px'; nd.style.top = n.y+'px'; }
    renderEdges(uid);
  }
  function endDrag(uid){
    var inst = G[uid];
    if(inst&&inst.drag){ setTimeout(function(){ inst._lastDownMoved = false; }, 0); }
    if(inst) inst.drag = null;
  }

  /* ---------- 连线 ---------- */
  function linkStart(ev, uid, id){
    ev.stopPropagation(); ev.preventDefault();
    var inst = G[uid];
    if(inst.linkFrom === id){ cancelLink(uid); return; }
    inst.linkFrom = id;
    var bar = el(uid+'_linkbar');
    bar.style.display='block';
    bar.innerHTML = '<span>⛓ 连线中：<b>'+inst.nodes.find(function(n){return n.id===id;}).name+'</b> → 点击目标节点完成（顺序线）。<a onclick="VC._linkKind(\''+uid+'\',\'branch\')">改分支线</a> · <a onclick="VC._linkKind(\''+uid+'\',\'dep\')">改依赖线</a> · <a onclick="VC._linkCancel(\''+uid+'\')">取消</a></span>';
    inst._linkKind = 'flow';
  }
  function finishLink(uid, toId){
    var inst = G[uid];
    var from = inst.linkFrom; cancelLink(uid);
    if(from===toId) return;
    if(inst.edges.some(function(e){return e.from===from&&e.to===toId;})) { UI.toast('该连线已存在','warn'); return; }
    var cycle = wouldCycle(inst.edges, from, toId);
    inst.edges.push({from:from, to:toId, kind:inst._linkKind||'flow'});
    renderEdges(uid);
    if(cycle) UI.toast('警告：形成环路，请检查流程方向', 'warn');
    else UI.toast('连线成功', 'ok');
    if(inst.cfg.onCanvasChange) inst.cfg.onCanvasChange();
  }
  function cancelLink(uid){
    var inst = G[uid]; inst.linkFrom = null;
    var bar = el(uid+'_linkbar'); if(bar) bar.style.display='none';
  }
  function wouldCycle(edges, from, to){
    var out = {}; edges.forEach(function(e){ (out[e.from]=out[e.from]||[]).push(e.to); });
    function reach(s, t, seen){
      if(s===t) return true; seen[s]=1;
      return (out[s]||[]).some(function(x){ return !seen[x] && reach(x, t, seen); });
    }
    return reach(to, from, {});
  }

  /* ---------- 公共 API ---------- */
  function dragStart(ev, uid, type){ ev.dataTransfer.setData('text/vc-type', type); }
  function zoom(uid, f){
    var inst = G[uid], inner = el(uid+'_inner');
    inst.scale = f===0? 1 : Math.min(2, Math.max(0.4, (inst.scale||1)*f));
    inner.style.transform = 'scale('+inst.scale+')';
  }
  function clear(uid){
    var inst = G[uid];
    UI.confirm('清空画布', '确定移除全部节点与连线？', function(){
      inst.nodes = []; inst.edges = []; render(uid);
    });
  }
  function addNode(uid, node){
    var inst = G[uid];
    inst.nodes.push(node); render(uid);
    if(inst.cfg.onCanvasChange) inst.cfg.onCanvasChange();
  }
  function delNode(uid, id){
    var inst = G[uid];
    inst.nodes = inst.nodes.filter(function(n){return n.id!==id;});
    inst.edges = inst.edges.filter(function(e){return e.from!==id&&e.to!==id;});
    render(uid);
    if(inst.cfg.onCanvasChange) inst.cfg.onCanvasChange();
  }
  function updateNode(uid, id, patch){
    var inst = G[uid];
    var n = inst.nodes.find(function(x){return x.id===id;});
    if(n) Object.assign(n, patch);
    render(uid);
  }
  function layout(uid){
    var inst = G[uid];
    var lv = topoLevels(inst.nodes, inst.edges);
    var byLv = {};
    inst.nodes.forEach(function(n){ (byLv[lv[n.id]] = byLv[lv[n.id]]||[]).push(n); });
    Object.keys(byLv).forEach(function(l){
      byLv[l].forEach(function(n, i){
        n.x = 60 + l*230; n.y = 40 + i*100;
      });
    });
    render(uid);
  }
  /* 标记节点（质量正常/异常、定位高亮等） */
  function mark(uid, id, mk){
    var inst = G[uid];
    var n = inst.nodes.find(function(x){return x.id===id;});
    if(n){ n.mark = mk; renderNodes(uid); }
  }
  function highlight(uid, id){
    var inst = G[uid]; inst.sel = id;
    renderNodes(uid);
    var nd = el(uid+'_n_'+id);
    if(nd && nd.scrollIntoView) nd.scrollIntoView({block:'nearest', inline:'nearest', behavior:'smooth'});
  }
  /* 校验：返回 [{level:'error'|'warn', msg}] */
  function validate(uid){
    var inst = G[uid], errs = [], map = {};
    inst.nodes.forEach(function(n){ map[n.id]=n; });
    var starts = inst.nodes.filter(function(n){return !inst.edges.some(function(e){return e.to===n.id;});});
    var ends = inst.nodes.filter(function(n){return !inst.edges.some(function(e){return e.from===n.id;});});
    var isolated = inst.nodes.filter(function(n){return !inst.edges.some(function(e){return e.from===n.id||e.to===n.id;});});
    if(!inst.nodes.length) errs.push({level:'error', msg:'画布为空，请先拖入元件'});
    isolated.forEach(function(n){ errs.push({level:'error', msg:'节点「'+n.name+'」未与任何节点连接'}); });
    if(inst.nodes.length>1 && starts.length>1) errs.push({level:'warn', msg:'存在 '+starts.length+' 个起始节点（'+starts.map(function(n){return n.name;}).join('、')+'），多入口请确认是否有意'});
    if(inst.nodes.length>1 && ends.length>1) errs.push({level:'warn', msg:'存在 '+ends.length+' 个出口节点，请确认流程收敛'});
    inst.nodes.forEach(function(n){
      var cnt = inst.edges.filter(function(e){return e.to===n.id;}).length;
      if(cnt>1 && !n.cfg['merge']) errs.push({level:'warn', msg:'节点「'+n.name+'」有 '+cnt+' 条输入，请确认汇聚语义'});
    });
    return errs;
  }
  function getData(uid){
    var inst = G[uid];
    return {nodes: JSON.parse(JSON.stringify(inst.nodes)), edges: JSON.parse(JSON.stringify(inst.edges))};
  }
  function setData(uid, data){
    var inst = G[uid];
    inst.nodes = data.nodes||[]; inst.edges = data.edges||[];
    inst.sel = null; render(uid);
  }
  function apiOf(uid){
    return {
      update:function(id, patch){ updateNode(uid, id, patch); },
      del:function(id){ delNode(uid, id); },
      data:function(){ return getData(uid); },
      layout:function(){ layout(uid); },
      validate:function(){ return validate(uid); },
      mark:function(id, m){ mark(uid, id, m); },
      highlight:function(id){ highlight(uid, id); }
    };
  }

  /* 拓扑序（供外部生成默认节点坐标） */
  /* 为一组节点生成默认网格坐标（未保存过坐标的新画布用） */
  function autoPos(nodes, edges){
    var lv = topoLevels(nodes, edges), byLv = {};
    nodes.forEach(function(n){ (byLv[lv[n.id]] = byLv[lv[n.id]]||[]).push(n); });
    Object.keys(byLv).forEach(function(l){ byLv[l].forEach(function(n,i){ n.x = 60+l*230; n.y = 40+i*100; }); });
    return nodes;
  }

  return {create:create, addNode:addNode, delNode:delNode, updateNode:updateNode, layout:layout, mark:mark, highlight:highlight, validate:validate, getData:getData, setData:setData, autoPos:autoPos,
    _dragStart:dragStart, _zoom:zoom, _clear:clear, _linkStart:linkStart, _linkKind:function(uid,k){G[uid]._linkKind=k;}, _linkCancel:cancelLink,
    _palToggle:function(uid, ci){
      var g = el(uid+'_catg'+ci); if(!g) return;
      g.classList.toggle('fold');
    },
    _palFilter:function(uid, kw){
      kw = (kw||'').trim().toLowerCase();
      var side = el(uid+'_side'); if(!side) return;
      var gs = side.querySelectorAll('.vc-cat-g');
      Array.prototype.forEach.call(gs, function(g){
        var vis = 0;
        Array.prototype.forEach.call(g.querySelectorAll('.vc-item'), function(it){
          var hit = !kw || (it.getAttribute('data-kw')||'').indexOf(kw)>=0;
          it.style.display = hit? '':'none';
          if(hit) vis++;
        });
        g.style.display = (kw && vis===0)? 'none':'';
      });
    }};
})();
