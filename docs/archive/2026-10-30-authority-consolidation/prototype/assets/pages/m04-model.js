/* ============================================================
   M04 数仓搭建与建模（P0：字段设计器/维度建模/物理化建表/版本管理/逆向工程/血缘影响/分层建模）
   可视化ER图一期暂缓（P0范围外）
   ============================================================ */
(function(){
var LAYERS = {ODS:'cyan', DWD:'blue', DWS:'purple', ADS:'green', DIM:'orange'};
App.reg('#/model/list', '数仓建模', function(){
  A._mdF = {layer:'', domain:''};
  var html = UI.pageHead('数仓搭建与建模',
    'ODS→DWD→DWS→ADS→DIM 分层建模；三阶段建模（概念→逻辑→物理）；重点支撑表间血缘关系（ER可视化一期暂缓）',
    '<button class="btn btn-primary" onclick="A.mdCreate()">+ 新建模型</button>'
    +'<button class="btn" onclick="A.mdAiWizard()">✦ AI 建表助手</button>'
    +'<button class="btn" onclick="App.go(\'#/model/reverse\')">逆向工程导入</button>',
    '操作指引：① 点击分层统计卡与业务域标签可双维筛选（再点取消）；② 「新建模型」进入字段设计器（三阶段：概念→逻辑→物理）；③ 「AI 建表助手」输入中文业务描述即可一键生成表与字段、自动稽核命名规范、自动关联维表/字典表；④ 物理化后模型进入版本管理与血缘影响分析。');
  html += UI.stateFlow([
    {k:'draft',  t:'概念/逻辑建模', d:'字段设计器 · 评审'},
    {k:'pub',    t:'已发布',        d:'字段冻结 · 可被引用'},
    {k:'built',  t:'已物理化',      d:'DDL 执行 · 自动分区'},
    {k:'prod',   t:'已投产',        d:'ETL/流任务引用 · 血缘受管'}
  ], null, '闭环说明：建模 →（评审发布）→ 已发布 →（物理化建表）→ 已投产；投产模型变更走版本管理（新版本→对比→发布），旧版本可回滚。');
  html += '<div id="mdLayerCards">'+A._mdLayerCards()+'</div>';
  html += '<div id="mdDomainBar">'+A._mdDomainBar()+'</div>';
  html += '<div class="banner banner-info" style="margin-top:14px"><span class="b-ico">ℹ</span><span>建模规范：<b>'+DB.dwLayers.map(function(l){return l.code+'（'+l.rule+'）';}).join('；')+'</b></span></div>';
  html += '<div id="mdListWrap">'+A._mdList()+'</div>';
  return html;
});
/* 分层 + 业务域双维筛选：统计卡点击筛选分层，分域Tab筛选业务域，两者可叠加（再点一次取消） */
A._mdF = {layer:'', domain:''};
A._mdDomains = function(){
  var seen = {}, out = [];
  DB.models.forEach(function(m){ if(m.bizDomain && !seen[m.bizDomain]){ seen[m.bizDomain] = 1; out.push(m.bizDomain); } });
  return out;
};
A._mdLayerCards = function(){
  var f = A._mdF;
  return '<div class="grid grid-5">'+DB.dwLayers.map(function(l){
    var cnt = DB.models.filter(function(m){return m.layer===l.code && (!f.domain || m.bizDomain===f.domain);}).length;
    var on = f.layer===l.code;
    return '<div class="stat-card hoverable"'+(on?' style="border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light)"':'')+' onclick="UI._mdLayerFilter(\''+l.code+'\')"><div><div class="stat-num" style="color:'+l.color+'">'+cnt+'</div><div class="stat-label"><b>'+l.code+'</b> '+l.name+(on?' <span class="tag tag-blue" style="height:16px">筛选中</span>':'')+'</div><div class="stat-sub" style="color:var(--text-3)">'+l.desc+'</div></div></div>';
  }).join('')+'</div>';
};
A._mdDomainBar = function(){
  var f = A._mdF;
  var chip = function(label, key, cnt, on){
    return '<span class="tag '+(on?'tag-blue':'tag-gray')+'" style="cursor:pointer;height:24px;line-height:24px;padding:0 12px;font-size:12px" onclick="UI._mdDomainFilter(\''+key+'\')">'+label+' · '+cnt+'</span>';
  };
  return '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:14px">'
    +'<span style="font-size:12.5px;color:var(--text-3)">业务域筛选：</span>'
    + chip('全部', '', DB.models.filter(function(m){return !f.layer || m.layer===f.layer;}).length, !f.domain)
    + A._mdDomains().map(function(d){
        return chip(d, d, DB.models.filter(function(m){return m.bizDomain===d && (!f.layer || m.layer===f.layer);}).length, f.domain===d);
      }).join('')
    +((f.layer||f.domain)? '<a style="font-size:12px;margin-left:4px" onclick="A._mdClearFilter()">重置筛选</a>':'')
    +'</div>';
};
UI._mdLayerFilter = function(code){
  A._mdF.layer = (A._mdF.layer===code)? '' : code;
  A._mdRefresh();
};
UI._mdDomainFilter = function(d){
  A._mdF.domain = (A._mdF.domain===d)? '' : d;
  A._mdRefresh();
};
A._mdClearFilter = function(){
  A._mdF.layer = ''; A._mdF.domain = '';
  A._mdRefresh();
};
A._mdRefresh = function(){
  var lc = document.getElementById('mdLayerCards'); if(lc) lc.innerHTML = A._mdLayerCards();
  var db = document.getElementById('mdDomainBar'); if(db) db.innerHTML = A._mdDomainBar();
  var lw = document.getElementById('mdListWrap'); if(lw) lw.innerHTML = A._mdList();
};
A._mdList = function(){
  var f = A._mdF;
  var list = DB.models.filter(function(m){ return (!f.layer || m.layer===f.layer) && (!f.domain || m.bizDomain===f.domain); });
  var cond = [];
  if(f.layer) cond.push(f.layer+'层');
  if(f.domain) cond.push(f.domain);
  return UI.card('逻辑模型列表'+(cond.length? '（'+cond.join(' · ')+' · '+list.length+'/'+DB.models.length+'）':'（全部 '+DB.models.length+' 张）'), UI.tbl({
    id:'t_md', rowKey:'id', pageSize:8, searchKeys:['name','code','bizDomain','owner'], searchPh:'搜索模型/表名',
    data:function(){ return list; },
    cols:[
      {t:'模型/表', k:'code', render:function(r){ return '<a onclick="App.go(\'#/model/design/'+r.id+'\')"><b class="mono">'+r.code+'</b></a><div style="font-size:11px;color:var(--text-3)">'+UI.esc(r.name)+' · v'+r.version+'</div>'; }},
      {t:'分层', k:'layer', render:function(r){ return tag(r.layer, LAYERS[r.layer]||'gray'); }},
      {t:'表类型', k:'type', render:function(r){ return r.type+'<div style="font-size:11px;color:var(--text-3)">'+(r.type==='事实表'?'星型模型（事务事实）':r.type==='维度表'?'星型模型（维度）':r.type==='宽表'?'宽表模型':'明细表')+'</div>'; }},
      {t:'引擎', k:'engine', render:function(r){ var e = DB.engineTypes.find(function(x){return x.name===r.engine;}); return r.engine+(e&&e.xc?' <span class="tag tag-xc" style="height:17px">信创</span>':''); }},
      {t:'业务域', k:'bizDomain'},
      {t:'字段数', render:function(r){ return r.fields.length; }},
      {t:'状态', k:'status', render:function(r){ return r.status==='draft'? st('draft') : st('published').replace('已发布','已物理化'); }},
      {t:'负责人', k:'owner'}
    ],
    ops:function(r){
      return '<a onclick="App.go(\'#/model/design/'+r.id+'\')">字段设计</a>'
        +'<a onclick="App.go(\'#/model/version/'+r.id+'\')">版本</a>'
        +'<a onclick="App.go(\'#/model/lineage/'+r.id+'\')">血缘影响</a>'
        +(r.status==='draft'?'<a onclick="A.mdPublish(\''+r.id+'\')">物理化建表</a>':'<a onclick="A.mdRebuild(\''+r.id+'\')">重新物理化</a>')
        +'<a class="danger" onclick="A.mdDel(\''+r.id+'\')">删除</a>';
    }
  }));
};
A.mdPublish = function(id){ A._mdPhys(id, true); };
A.mdRebuild = function(id){ A._mdPhys(id, false); };
A._mdPhys = function(id, first){
  var m = DB.models.find(function(x){return x.id===id;});
  var ddl = A.mdGenDDL(m);
  UI.modal({title:(first?'物理化建表':'重新物理化')+' - '+m.code, w:'w-xl', body:
    '<div class="form-grid" style="max-width:700px">'
    + UI.fSelect('目标引擎', 'ph_engine', DB.engineTypes.map(function(e){return {v:e.name, t:e.name+(e.xc?'（信创·'+e.ddl+'）':'（'+e.ddl+'）')};}), {value:m.engine, onchange:'A.mdDdlRefresh(\''+id+'\')'})
    + UI.fSelect('执行方式', 'ph_mode', [{v:'exec',t:'直接执行建表'},{v:'script',t:'导出DDL脚本（手工执行）'}], {value:'exec', onchange:'A.mdDdlRefresh(\''+id+'\')'})
    + '</div>'
    + '<div class="f-label">DDL预览（一键生成，可编辑）</div><div class="code-box" id="ph_ddl" contenteditable="true">'+UI.esc(ddl)+'</div>',
    footer:'<button class="btn" onclick="UI.closeModal()">取消</button><button class="btn" onclick="UI.download(\''+m.code+'.sql\', document.getElementById(\'ph_ddl\').innerText)">⇩ 导出DDL</button><button class="btn btn-primary" onclick="A.mdPhysExec(\''+id+'\')">执行建表</button>'});
};
A.mdDdlRefresh = function(id){
  var m = DB.models.find(function(x){return x.id===id;});
  m.engine = UI.val('ph_engine');
  document.getElementById('ph_ddl').innerText = A.mdGenDDL(m);
  UI.toast('已按 '+m.engine+' 方言重新生成 DDL', 'info');
};
A.mdGenDDL = function(m){
  var isDoris = m.engine.indexOf('Doris')>=0 || m.engine==='万里 GreatDB';
  var cols = m.fields.map(function(f){
    var t = f.t + (f.len&&f.len!=='' ? (String(f.len).charAt(0)==='('?'':'('+f.len+')') : '');
    return '  '+f.n+' '+t + (isDoris&&f.pk?'':'') + (f.cmt?' COMMENT \''+f.cmt+'\'':'');
  }).join(',\n');
  var part = m.fields.find(function(f){return f.pkPart;});
  var s = 'CREATE TABLE '+m.code+' (\n'+cols+'\n)\n';
  if(part) s += 'PARTITION BY '+part.n+'\n';
  if(isDoris) s += 'DISTRIBUTED BY HASH('+ (m.fields.find(function(f){return f.pk;})||{n:m.fields[0].n}).n +') BUCKETS 10\nPROPERTIES("replication_num"="3");';
  else s += 'COMMENT \''+m.name+'\';';
  return s;
};
A.mdPhysExec = function(id){
  var m = DB.models.find(function(x){return x.id===id;});
  UI.closeModal();
  UI.toast('正在执行建表到 '+m.engine+' ...', 'info');
  setTimeout(function(){
    m.status = 'published';
    UI.toast('建表成功：'+m.code+'（'+m.engine+'），模型已与ETL任务建立血缘关联', 'success');
    App.resolve();
  }, 1100);
};
A.mdCreate = function(){
  UI.drawer({title:'新建逻辑模型', w:'w-lg', body:
    UI.fInput('模型名称', 'm_name', {req:true, ph:'如：订单支付明细表'})
    + UI.fInput('表名', 'm_code', {req:true, value:'', ph:'dwd_order_pay_detail', help:'命名规范 NR-02：dwd_[业务域]_[业务过程]'})
    + UI.fSelect('数仓分层', 'm_layer', DB.dwLayers.map(function(l){return {v:l.code, t:l.code+' '+l.name};}), {value:'DWD', onchange:'A.mdLayerHint()'})
    + UI.fSelect('引擎', 'm_engine', DB.engineTypes.map(function(e){return {v:e.name, t:e.name};}), {value:'Apache Doris'})
    + UI.fRadio('建模类型', 'm_type', [{v:'fact',t:'事实表（星型）'},{v:'dim',t:'维度表（星型/雪花）'},{v:'wide',t:'宽表（ADS）'}], 'fact')
    + UI.fSelect('业务域', 'm_domain', ['交易域','经营域','财务域','商品域','公共'], {value:'交易域'})
    + '<div id="mdLayerHint" class="lock-tip">DWD规范：一个业务过程一张表，字段使用snake_case，主键+分区字段必填</div>',
    onOk:function(){
      var id = 'MD'+String(DB.models.length+1).padStart(3,'0');
      DB.models.push({id:id, name:UI.val('m_name'), code:UI.val('m_code'), layer:UI.val('m_layer'), engine:UI.val('m_engine'),
        type:{fact:'事实表',dim:'维度表',wide:'宽表'}[UI.radioVal('m_type','fact')], status:'draft',
        fields:[{n:'id',t:'BIGINT',len:'',pk:true,pkPart:false,cmt:'主键',def:''},{n:'dt',t:'DATE',len:'',pk:false,pkPart:true,cmt:'分区字段',def:''}],
        version:1, owner:DB.user.name, bizDomain:UI.val('m_domain'), updatedAt:'2026-09-12 22:50',
        versions:[{v:1,date:'2026-09-12 22:50',author:DB.user.name,note:'初版（字段设计器创建）',status:'当前版本'}]});
      UI.toast('模型已创建（草稿），进入字段设计器', 'success');
      setTimeout(function(){ App.go('#/model/design/'+id); }, 300);
    }});
};
A.mdLayerHint = function(){
  var l = DB.dwLayers.find(function(x){return x.code===UI.val('m_layer');});
  var el = document.getElementById('mdLayerHint');
  if(el && l) el.innerText = l.code+'规范：'+l.rule;
};
A.mdDel = function(id){
  var m = DB.models.find(function(x){return x.id===id;});
  UI.delRow(DB.models, 'id', id, m.name);
};

/* ============ AI 建表助手（三步式：①输入 → ②生成与稽核 → ③维表/字典关联 → 应用到模型） ============ */
A._aiKw = [['支付','pay'],['退款','refund'],['订单','order'],['结算','settle'],['商品','product'],['库存','stock'],['用户','user'],['会员','member'],['物流','delivery'],['发货','delivery'],['优惠券','coupon'],['营销','marketing'],['预算','budget'],['凭证','voucher'],['充值','recharge'],['提现','withdraw']];
A._aiDomSlug = {'交易域':'trade','经营域':'biz','商品域':'item','财务域':'fin','公共':'comm'};
A.mdAiWizard = function(modelId){
  var m = modelId? DB.models.find(function(x){return x.id===modelId;}) : null;
  A._aiWiz = {step:1, modelId:modelId||'', gen:false, dict:false, result:null,
    form:{ name: m? m.name:'', desc:'', ref: m? m.code:'', layer:(m && m.layer!=='ODS')? m.layer:'DWD', domain: m? m.bizDomain:'交易域' }};
  UI.drawer({title:'✦ AI 建表助手', w:'w-lg', footer:false, body:'<div id="mdAiBody"></div>', onMount:function(){ A.mdAiRender(); }});
};
A.mdAiRender = function(){
  var w = A._aiWiz, el = document.getElementById('mdAiBody');
  if(!el) return;
  var html = UI.steps(['输入需求','生成与稽核','维表/字典关联'], w.step-1);
  if(w.step===1){
    html += UI.fInput('表名中文提示', 'mdai_name', {req:true, value:w.form.name, ph:'如：支付明细事实表'})
      + UI.fTextarea('业务描述', 'mdai_desc', {rows:3, value:w.form.desc, ph:'描述业务过程、粒度与分析维度，如：记录每笔支付成功/失败的明细，按天分区，分析渠道与门店维度'})
      + UI.fSelect('参考表 / 对标语句', 'mdai_ref', [{v:'',t:'（不参考，直接生成）'}].concat(DB.models.map(function(x){return {v:x.code, t:x.code+'（'+x.name+'）'};})), {value:w.form.ref, help:'可留空；选择已有表作为对标，AI 将参考其建模风格'})
      + UI.fSelect('目标分层', 'mdai_layer', ['DWD','DWS','ADS','DIM'].map(function(l){ var lo = DB.dwLayers.find(function(x){return x.code===l;}); return {v:l, t:l+' '+lo.name}; }), {value:w.form.layer, onchange:'A.mdAiLayerHint()'})
      + UI.fSelect('业务域', 'mdai_domain', A._mdDomains(), {value:w.form.domain})
      + '<div class="lock-tip" id="mdAiLayerHint"></div>';
  } else if(w.step===2){
    html += A._aiStep2();
  } else {
    html += A._aiStep3();
  }
  html += '<div style="border-top:1px solid var(--border,#e6e9f0);margin-top:16px;padding-top:12px;display:flex;gap:8px;justify-content:flex-end">'
    + (w.step===1
      ? '<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.mdAiStep(2)">下一步 →</button>'
      : w.step===2
      ? '<button class="btn" onclick="A.mdAiStep(1)">← 上一步</button><button class="btn" onclick="A.mdAiGenerate()">'+(w.gen?'↻ 重新生成':'✦ 生成')+'</button><button class="btn btn-primary" onclick="A.mdAiStep(3)">下一步：关联稽核 →</button>'
      : '<button class="btn" onclick="A.mdAiStep(2)">← 上一步</button><button class="btn btn-primary" onclick="A.mdAiApply()">✓ 应用到模型</button>')
    + '</div>';
  el.innerHTML = html;
  if(w.step===1) A.mdAiLayerHint();
};
A.mdAiStep = function(n){
  var w = A._aiWiz;
  if(w.step===1 && n>1){
    w.form.name = UI.val('mdai_name'); w.form.desc = UI.val('mdai_desc');
    w.form.ref = UI.val('mdai_ref'); w.form.layer = UI.val('mdai_layer'); w.form.domain = UI.val('mdai_domain');
    if(!w.form.name){ UI.toast('请先填写表名中文提示', 'warn'); return; }
  }
  if(n===3 && !w.gen){ UI.toast('请先点击「✦ 生成」产出 AI 结果', 'warn'); return; }
  w.step = n;
  A.mdAiRender();
};
A.mdAiLayerHint = function(){
  var l = DB.dwLayers.find(function(x){return x.code===UI.val('mdai_layer');});
  var el = document.getElementById('mdAiLayerHint');
  if(el && l){
    var nr = {DWD:'NR-02', DWS:'NR-03', ADS:'NR-04'}[l.code];
    el.innerText = l.code+'规范'+(nr?'（'+nr+'）':'')+'：'+l.rule;
  }
};
/* 按输入拼装：物理表名（分层前缀+业务域+业务过程+后缀，符合命名规范 NR-02/03/04） */
A._aiGenCode = function(layer, dom, proc){
  var d = A._aiDomSlug[dom]||'gen', p = proc||'info';
  if(layer==='DWD') return 'dwd_'+d+'_'+p+'_detail';
  if(layer==='DWS') return 'dws_'+d+'_'+p+'_1d';
  if(layer==='ADS') return 'ads_'+d+'_'+p+'_report';
  return 'dim_'+(proc||d);
};
/* 自动初始化字段：主键id、业务键、维度外键、度量、标准审计字段etl_time，8-12个 */
A._aiGenFields = function(layer, p, cn){
  p = p||'biz';
  var fs = [];
  var F = function(n, t, len, cmt, pk, pkPart){ fs.push({n:n, t:t, len:len==null?'':len, pk:!!pk, pkPart:!!pkPart, cmt:cmt, def:''}); };
  F('id','BIGINT','','主键（代理键）', true, false);
  if(layer==='DWD'){
    F(p+'_no','VARCHAR',32, cn+'单号（业务键）');
    F('order_id','BIGINT','','订单ID（维度外键）');
    F('user_id','BIGINT','','用户ID（关联 dim_user）');
    F('shop_id','BIGINT','','门店ID（关联 dim_shop）');
    F(p+'_amount','DECIMAL','(18,2)', cn+'金额（度量）');
    F(p+'_status','TINYINT','', cn+'状态 1成功 0失败');
    F(p+'_channel','VARCHAR',20, cn+'渠道');
  } else if(layer==='DWS'){
    F('stat_date','DATE','','统计日期（粒度：天）', true, false);
    F('user_id','BIGINT','','用户ID（维度外键）');
    F('shop_id','BIGINT','','门店ID（维度外键）');
    F(p+'_order_cnt','BIGINT','', cn+'订单数（度量）');
    F(p+'_user_cnt','BIGINT','', cn+'用户数（度量）');
    F(p+'_amount_sum','DECIMAL','(18,2)', cn+'金额合计（度量）');
  } else if(layer==='ADS'){
    F('stat_date','DATE','','统计日期', true, false);
    F(p+'_amount','DECIMAL','(18,2)', cn+'金额（应用指标）');
    F(p+'_order_cnt','BIGINT','', cn+'订单数（应用指标）');
    F(p+'_user_cnt','BIGINT','', cn+'用户数（应用指标）');
    F(p+'_amount_mom','DECIMAL','(18,2)', cn+'金额环比');
  } else {
    F(p+'_code','VARCHAR',32, cn+'编码（业务键）');
    F(p+'_name','VARCHAR',100, cn+'名称');
    F('parent_id','BIGINT','','父级ID');
    F('sort_no','INT','','排序号');
    F('is_valid','TINYINT','','是否有效 1是 0否');
    F('remark','VARCHAR',200,'备注');
  }
  F('etl_time','DATETIME','','ETL写入时间（标准审计字段）');
  if(layer!=='DIM') F('dt','DATE','','天分区字段', false, true);
  return fs;
};
A._aiFieldAudit = function(f){ return /^[a-z][a-z0-9_]*$/.test(f.n); };
A._aiGenAssoc = function(fs, dict){
  var has = function(n){ return fs.some(function(f){return f.n===n;}); };
  var a = [];
  if(has('user_id')) a.push({f:'user_id', t:'dim_user', st:'ok', note:'已有维表 · 会员维，代理键关联'});
  if(has('shop_id')) a.push({f:'shop_id', t:'dim_shop', st:'ok', note:'已有维表 · 门店维，代理键关联'});
  if(dict && has('pay_type')) a.push({f:'pay_type', t:'dim_dict_pay_type', st:'gen', note:'未发现字典表 → 已按命名规范自动生成并关联'});
  return a;
};
A.mdAiGenerate = function(){
  var w = A._aiWiz, f = w.form, i, kw = null;
  var text = (f.name||'')+' '+(f.desc||'');
  for(i=0;i<A._aiKw.length;i++){ if(text.indexOf(A._aiKw[i][0])>=0){ kw = A._aiKw[i]; break; } }
  var proc = kw? kw[1] : '', procCn = kw? kw[0] : '业务';
  var fields = A._aiGenFields(f.layer, proc, procCn);
  w.dict = /支付类型|状态类/.test(text);
  if(w.dict && f.layer==='DWD'){
    var pos = fields.length;
    for(i=0;i<fields.length;i++){ if(fields[i].n==='etl_time'){ pos = i; break; } }
    fields.splice(pos, 0, {n:'pay_type', t:'VARCHAR', len:20, pk:false, pkPart:false, cmt:'支付类型（编码，对照 dim_dict_pay_type）', def:''});
  }
  w.result = {code:A._aiGenCode(f.layer, f.domain, proc), layer:f.layer, domain:f.domain, name:f.name, ref:f.ref, fields:fields, assoc:A._aiGenAssoc(fields, w.dict && f.layer==='DWD')};
  w.gen = true;
  A.mdAiRender();
  UI.toast('AI 已生成 '+w.result.code+'（'+fields.length+' 字段），稽核通过，请确认', 'success');
};
A._aiStep2 = function(){
  var w = A._aiWiz;
  if(!w.gen){
    return '<div class="empty" style="padding:28px"><span class="e-ico">✦</span><p>点击下方「✦ 生成」，AI 将根据输入'+(w.form.ref?'参考 <b class="mono">'+UI.esc(w.form.ref)+'</b> ':'')+'自动生成物理表名与字段清单，并逐条稽核命名规范。</p></div>';
  }
  var r = w.result;
  var okCnt = r.fields.filter(function(f){return A._aiFieldAudit(f);}).length;
  var nr = {DWD:'NR-02', DWS:'NR-03', ADS:'NR-04'}[r.layer];
  var lobj = DB.dwLayers.find(function(x){return x.code===r.layer;});
  var msg = 'AI 建表助手已生成 '+r.fields.length+' 字段、'+r.assoc.length+' 关联，稽核通过 '+(okCnt+1+r.assoc.length)+' 项：\n'
    +'① 物理表名 '+r.code+' 符合 '+r.layer+' 层命名规范'+(nr?'（'+nr+'）':'')+' ✓\n'
    +'② 字段命名 '+okCnt+'/'+r.fields.length+' 符合 snake_case 规范（NR-05）✓\n'
    +'③ 维表/字典关联已就绪，可在第③步确认后应用到模型';
  var html = '<div class="banner banner-info"><span class="b-ico">✦</span><span>由 Datara 智能助手生成 · 可人工修正后应用</span>'
    +'<button class="btn btn-sm" style="margin-left:auto" onclick="AI.show(\''+msg.replace(/\n/g,'\\n')+'\')">在 AI 助手中查看</button></div>';
  html += UI.desc([
    ['物理表名', '<b class="mono">'+r.code+'</b> '+tag('命名规范稽核 ✓','green')],
    ['目标分层', r.layer+' '+lobj.name+'（稽核依据：'+(nr||'dim_维度名，全局唯一')+'）'],
    ['业务域 / 参考表', r.domain+(r.ref?' / <span class="mono">'+UI.esc(r.ref)+'</span>':' / 无')]
  ]);
  html += '<div class="f-label" style="margin-top:12px">字段清单（'+r.fields.length+' 个，逐条命名稽核 NR-05）</div>';
  html += '<div class="table-wrap"><table class="tbl"><thead><tr><th style="width:40px">序</th><th>字段名</th><th>类型</th><th>注释</th><th style="width:52px">主键</th><th style="width:64px">分区键</th><th style="width:104px">稽核</th></tr></thead><tbody>'
    + r.fields.map(function(f, i){
        var ok = A._aiFieldAudit(f);
        return '<tr><td>'+(i+1)+'</td><td><span class="mono">'+f.n+'</span></td>'
          +'<td>'+f.t+(f.len? (String(f.len).charAt(0)==='('? f.len : '('+f.len+')') : '')+'</td>'
          +'<td>'+UI.esc(f.cmt)+'</td><td>'+(f.pk?'✓':'')+'</td><td>'+(f.pkPart?'✓':'')+'</td>'
          +'<td>'+(ok? '<span style="color:var(--success)">✓ 命名合规</span>' : '<span style="color:var(--danger)">✗ 命名违规</span>')+'</td></tr>';
      }).join('')
    +'</tbody></table></div>';
  html += '<div class="f-help" style="margin-top:8px">稽核汇总：表名 '+r.layer+' 层命名规范 ✓ · 字段 '+okCnt+'/'+r.fields.length+' 合规 ✓ · 类型映射 '+r.fields.length+'/'+r.fields.length+' ✓（DECIMAL 带精度、VARCHAR 带长度、含 etl_time 审计字段与 dt 分区字段）</div>';
  return html;
};
A._aiStep3 = function(){
  var w = A._aiWiz, r = w.result;
  var html = '<div class="banner banner-info"><span class="b-ico">✦</span><span>由 Datara 智能助手生成 · 可人工修正后应用</span></div>';
  html += UI.card('维表 / 字典自动关联稽核（'+r.assoc.length+' 项）',
    r.assoc.map(function(a){
      return '<div class="checker-line'+(a.st==='ok'?' ok':'')+'"><span>▦</span><b class="mono">'+a.f+'</b><span style="color:var(--text-3)">→</span><b class="mono">'+a.t+'</b>'
        +(a.st==='gen'? ' '+tag('自动生成','orange') : ' '+tag('已有关联','green'))
        +'<span style="margin-left:auto;color:var(--text-3);font-size:12px">'+UI.esc(a.note)+' '+(a.st==='gen'?'✓':'√')+'</span></div>';
    }).join('') || '<div class="empty" style="padding:16px"><p>未识别到可关联的维度外键</p></div>');
  var tgt = w.modelId? (DB.models.find(function(x){return x.id===w.modelId;})||{}).code : null;
  html += '<div class="banner banner-info" style="margin-top:10px"><span class="b-ico">ℹ</span><span>应用后：'+(tgt? '字段将合并进当前模型 <b class="mono">'+tgt+'</b>（同名字段自动跳过）' : '将创建新模型草稿（'+r.layer+' 层 · '+r.domain+'）')+'；关联维表信息已写入字段注释，便于血缘识别。</span></div>';
  if(r.assoc.some(function(a){return a.st==='gen';})){
    html += '<div class="banner banner-warn" style="margin-top:8px"><span class="b-ico">⚠</span><span>检测到自动生成的字典表 <b class="mono">dim_dict_pay_type</b>，应用时将同步创建为 DIM 层草稿，形成建模闭环。</span></div>';
  }
  return html;
};
A.mdAiApply = function(){
  var w = A._aiWiz;
  if(!w || !w.gen){ UI.toast('请先点击「✦ 生成」', 'warn'); return; }
  var r = w.result, now = '2026-09-13 10:20';
  var m = w.modelId? DB.models.find(function(x){return x.id===w.modelId;}) : null;
  var added = 0, skipped = 0;
  if(m){
    r.fields.forEach(function(f){
      if(m.fields.some(function(x){return x.n===f.n;})){ skipped++; return; }
      m.fields.push({n:f.n, t:f.t, len:f.len, pk:f.pk, pkPart:f.pkPart, cmt:f.cmt, def:f.def||''});
      added++;
    });
    m.updatedAt = now;
    UI.toast('AI 结果已应用：'+m.code+' 新增 '+added+' 字段'+(skipped? '（跳过 '+skipped+' 个同名字段）':''), 'success');
  } else {
    var id = 'MD'+String(DB.models.length+1).padStart(3,'0');
    var typeMap = {DWD:'事实表', DWS:'汇总表', ADS:'宽表', DIM:'维度表'};
    m = {id:id, name:r.name||r.code, code:r.code, layer:r.layer, engine:'Apache Doris', type:typeMap[r.layer]||'明细表', status:'draft',
      fields: r.fields.map(function(f){ return {n:f.n, t:f.t, len:f.len, pk:f.pk, pkPart:f.pkPart, cmt:f.cmt, def:f.def||''}; }),
      version:1, owner:DB.user.name, bizDomain:r.domain, updatedAt:now,
      versions:[{v:1, date:now, author:DB.user.name, note:'AI 建表助手生成（稽核通过 '+(r.fields.length+1+r.assoc.length)+' 项）', status:'当前版本'}]};
    DB.models.push(m);
    UI.toast('已创建模型草稿 '+m.code+'（AI 生成 '+m.fields.length+' 字段），可进入字段设计器微调', 'success');
  }
  if(r.assoc.some(function(a){return a.st==='gen';}) && !DB.models.some(function(x){return x.code==='dim_dict_pay_type';})){
    DB.models.push({id:'MD'+String(DB.models.length+1).padStart(3,'0'), name:'支付类型字典表', code:'dim_dict_pay_type', layer:'DIM', engine:'Apache Doris', type:'维度表', status:'draft',
      fields:[
        {n:'id',t:'BIGINT',len:'',pk:true,pkPart:false,cmt:'主键',def:''},
        {n:'pay_type_code',t:'VARCHAR',len:20,pk:false,pkPart:false,cmt:'支付类型编码',def:''},
        {n:'pay_type_name',t:'VARCHAR',len:50,pk:false,pkPart:false,cmt:'支付类型名称',def:''},
        {n:'sort_no',t:'INT',len:'',pk:false,pkPart:false,cmt:'排序号',def:'0'},
        {n:'is_valid',t:'TINYINT',len:'',pk:false,pkPart:false,cmt:'是否有效 1是 0否',def:'1'},
        {n:'etl_time',t:'DATETIME',len:'',pk:false,pkPart:false,cmt:'ETL写入时间',def:''},
        {n:'dt',t:'DATE',len:'',pk:false,pkPart:true,cmt:'分区字段',def:''}],
      version:1, owner:DB.user.name, bizDomain:'公共', updatedAt:now,
      versions:[{v:1, date:now, author:DB.user.name, note:'AI 建表助手按命名规范自动生成', status:'当前版本'}]});
    UI.toast('已同步创建字典表 dim_dict_pay_type（DIM 层草稿）', 'info');
  }
  UI.closeDrawer();
  App.resolve();
};

/* 字段设计器 */
App.reg('#/model/design/:id', '字段设计器', function(p){
  var m = DB.models.find(function(x){return x.id===p.id;});
  if(!m) return '<div class="empty">模型不存在</div>';
  var html = UI.pageHead('<a onclick="App.go(\'#/model/list\')">← 数仓建模</a> / '+m.code,
    UI.esc(m.name)+' · '+tag(m.layer, LAYERS[m.layer])+' · '+m.engine+' · v'+m.version+' · '+m.bizDomain+' · 负责人 '+m.owner,
    '<button class="btn" onclick="A.mdAiWizard(\''+m.id+'\')">✦ AI 建表助手</button>'
    +'<button class="btn" onclick="A.mdAddField(\''+m.id+'\')">+ 添加字段</button>'
    +'<button class="btn" onclick="A.mdSaveVer(\''+m.id+'\')">保存新版本</button>'
    +'<button class="btn btn-primary" onclick="A.mdPublish(\''+m.id+'\')">物理化建表</button>'
    + (m.status==='draft'? st('draft') : st('published').replace('已发布','已物理化')));
  html += UI.card('字段设计（表单化：字段名/类型/长度/默认值/注释/主键/分区键）',
    '<div class="table-wrap"><table class="tbl" id="mdFieldTbl"><thead><tr>'
    +'<th style="width:44px">序</th><th>字段名 *</th><th>类型</th><th>长度/精度</th><th>默认值</th><th>注释</th><th style="width:64px">主键</th><th style="width:76px">分区键</th><th style="width:60px">操作</th>'
    +'</tr></thead><tbody>'
    + m.fields.map(function(f, i){
      return '<tr>'
        +'<td>'+(i+1)+'</td>'
        +'<td><input class="inp" style="width:150px" value="'+f.n+'" onchange="A.mdFieldChg('+i+',\'n\',this.value)"></td>'
        +'<td><select class="sel" style="width:130px" onchange="A.mdFieldChg('+i+',\'t\',this.value)">'
        + ['BIGINT','VARCHAR','CHAR','DECIMAL','DATETIME','DATE','INT','TINYINT','DOUBLE','TEXT'].map(function(t){return '<option '+(f.t===t?'selected':'')+'>'+t+'</option>';}).join('')
        +'</select></td>'
        +'<td><input class="inp" style="width:100px" value="'+f.len+'" onchange="A.mdFieldChg('+i+',\'len\',this.value)"></td>'
        +'<td><input class="inp" style="width:90px" value="'+f.def+'" onchange="A.mdFieldChg('+i+',\'def\',this.value)"></td>'
        +'<td><input class="inp" style="width:180px" value="'+UI.esc(f.cmt)+'" onchange="A.mdFieldChg('+i+',\'cmt\',this.value)"></td>'
        +'<td><input type="checkbox" class="row-check" '+(f.pk?'checked':'')+' onchange="A.mdFieldChg('+i+',\'pk\',this.checked)"></td>'
        +'<td><input type="checkbox" class="row-check" '+(f.pkPart?'checked':'')+' onchange="A.mdFieldChg('+i+',\'pkPart\',this.checked)"></td>'
        +'<td><a class="danger" onclick="A.mdDelField(\''+m.id+'\','+i+')">删除</a></td>'
        +'</tr>';
    }).join('')
    +'</tbody></table></div>'
    +'<div style="margin-top:10px;display:flex;gap:8px;align-items:center"><button class="btn btn-sm" onclick="A.mdAddField(\''+m.id+'\')">+ 添加字段</button><span class="f-help">规范：字段命名 snake_case（NR-05），每层建模模板自动校验命名合规</span></div>');
  html += UI.card('DDL预览（'+m.engine+' 方言）', '<div class="code-box">'+UI.esc(A.mdGenDDL(m))+'</div>'
    +'<div style="margin-top:10px;display:flex;gap:8px"><button class="btn" onclick="UI.download(\''+m.code+'.sql\',\''+UI.esc(A.mdGenDDL(m)).replace(/\n/g,'\\n')+'\')">⇩ 导出DDL</button><button class="btn" onclick="App.go(\'#/model/reverse\')">从数据源反向生成</button></div>');
  html += UI.card('维度建模建议（自动识别）',
    '<div class="grid grid-3">'
    +'<div class="stat-card"><div><b>星型模型</b><div class="f-help">事实表 dwd_order_pay_detail 关联维度 dim_user / dim_product；当前库已识别 2 个维度关联</div></div></div>'
    +'<div class="stat-card"><div><b>雪花模型</b><div class="f-help">dim_user → dim_org 二级维度，可接受1层雪花</div></div></div>'
    +'<div class="stat-card"><div><b>宽表模型</b><div class="f-help">ADS层 ads_kpi_report 建议采用宽表冗余常用维度</div></div></div></div>');
  return html;
});
A.mdFieldChg = function(i, k, v){
  var m = DB.models.find(function(x){return x.id===App.cur.params.id;});
  m.fields[i][k] = (k==='pk'||k==='pkPart')? !!v : v;
};
A.mdAddField = function(id){
  var m = DB.models.find(function(x){return x.id===id;});
  m.fields.push({n:'field_'+(m.fields.length+1), t:'VARCHAR', len:100, pk:false, pkPart:false, cmt:'', def:''});
  UI.toast('已添加字段，请完善定义', 'success'); App.resolve();
};
A.mdDelField = function(id, i){
  var m = DB.models.find(function(x){return x.id===id;});
  UI.confirm({title:'删除字段', danger:true, msg:'确认删除字段「'+m.fields[i].n+'」？', onOk:function(){ m.fields.splice(i,1); UI.toast('字段已删除', 'success'); App.resolve(); }});
};
A.mdSaveVer = function(id){
  var m = DB.models.find(function(x){return x.id===id;});
  UI.drawer({title:'保存新版本 - '+m.code, body:
    UI.fTextarea('变更说明', 'sv_note', {rows:3, req:true, ph:'本次变更内容，将写入版本历史'})
    + '<div class="f-help">当前版本 v'+m.version+' → 保存后生成 v'+(m.version+1)+'；历史版本支持对比与回滚</div>',
    onOk:function(){
      m.version++;
      m.versions.push({v:m.version, date:'2026-09-12 22:52', author:DB.user.name, note:UI.val('sv_note')||'字段调整', status:'当前版本'});
      m.versions.forEach(function(v){ v.status = v.v===m.version?'当前版本':'历史'; });
      m.updatedAt = '2026-09-12 22:52';
      UI.toast('已保存 v'+m.version+'，可到「版本管理」对比与回滚', 'success');
      App.resolve();
    }});
};

/* 版本管理 */
App.reg('#/model/version/:id', '模型版本管理', function(p){
  var m = DB.models.find(function(x){return x.id===p.id;});
  if(!m) return '<div class="empty"><span class="e-ico">⌀</span><p>模型不存在，请从模型列表进入</p><a onclick="App.go(\'#/model/list\')">返回列表</a></div>';
  var html = UI.pageHead('<a onclick="App.go(\'#/model/list\')">← 数仓建模</a> / 版本管理 - '+m.code,
    '变更历史 / 版本对比 / 回滚到历史版本');
  html += UI.card('版本历史（共 '+m.versions.length+' 个版本）', UI.tbl({
    id:'t_mdv', rowKey:'v', pageSize:6, searchKeys:['note'],
    data:function(){ return m.versions; },
    cols:[
      {t:'版本', render:function(r){ return '<b>v'+r.v+'</b>'+(r.v===m.version?' '+tag('当前','green'):tag('历史','gray')); }},
      {t:'时间', k:'date'},
      {t:'操作人', k:'author'},
      {t:'变更说明', k:'note'}
    ],
    ops:function(r){
      return '<a onclick="A.mdCompare(\''+m.id+'\','+r.v+')">对比当前</a>'
        +(r.v===m.version?'':'<a onclick="A.mdRollback(\''+m.id+'\','+r.v+')">回滚此版本</a>')
        +'<a onclick="UI.download(\''+m.code+'_v'+r.v+'.sql\',\'-- 版本 v'+r.v+' DDL 快照\\n\'+\''+UI.esc(A.mdGenDDL(m)).replace(/\n/g,'\\n')+'\')">DDL快照</a>';
    }
  }));
  html += '<div id="mdCmpBox"></div>';
  return html;
});
A.mdCompare = function(id, v){
  var m = DB.models.find(function(x){return x.id===id;});
  document.getElementById('mdCmpBox').innerHTML = UI.card('版本对比：v'+v+' vs v'+m.version+'（当前）',
    '<div class="grid grid-2">'
    +'<div><div class="f-label" style="font-weight:600;margin-bottom:6px">v'+v+'（历史）</div><div class="code-box">'+UI.esc(A.mdGenDDL(m)).replace(/gender|pay_channel/g,'<span style="text-decoration:line-through;color:#f87171">$&</span>')+'</div></div>'
    +'<div><div class="f-label" style="font-weight:600;margin-bottom:6px">v'+m.version+'（当前）</div><div class="code-box">'+UI.esc(A.mdGenDDL(m)).replace(/gender|pay_channel/,'<span style="background:rgba(22,163,74,.15);color:#16a34a;font-weight:600">$&</span>')+'</div></div></div>'
    +'<div class="banner banner-info" style="margin-top:10px"><span class="b-ico">ℹ</span><span>差异项已高亮（绿色为当前版本新增字段）。</span></div>');
  document.getElementById('mdCmpBox').scrollIntoView({behavior:'smooth'});
};
A.mdRollback = function(id, v){
  UI.confirm({title:'回滚版本', msg:'确认回滚到 v'+v+'？', detail:'将基于 v'+v+' 生成新版本（不覆盖历史），并提示下游影响。', onOk:function(){
    var m = DB.models.find(function(x){return x.id===id;});
    m.version++;
    m.versions.push({v:m.version, date:'2026-09-12 22:53', author:DB.user.name, note:'回滚至 v'+v+' 快照', status:'当前版本'});
    m.versions.forEach(function(x){ x.status = x.v===m.version?'当前版本':'历史'; });
    UI.toast('已回滚：生成新版本 v'+m.version+'；下游 3 个任务已收到变更影响提示', 'success');
    App.resolve();
  }});
};

/* 逆向工程 */
App.reg('#/model/reverse', '逆向工程', function(){
  var html = UI.pageHead('逆向工程', '从已有数据库表反向生成逻辑模型（ER可视化一期暂缓，以表结构导入方式实现）');
  html += UI.card('第一步：选择数据源与库表', UI.tbl({
    id:'t_rev', rowKey:'name', pageSize:8, searchKeys:['name','type'],
    data:function(){ return DB.datasources.filter(function(d){return d.type!=='Kafka';}); },
    cols:[{t:'数据源',render:function(r){return '<b>'+UI.esc(r.name)+'</b><div style="font-size:11px;color:var(--text-3)">'+r.type+' · '+UI.esc(r.host)+'</div>';}},{t:'环境',k:'env'},{t:'状态',k:'status',render:function(r){return st(r.status);}}],
    ops:function(r){ return '<a onclick="A.revScan(\''+r.id+'\')">扫描库表 →</a>'; }
  }));
  html += '<div id="revStep2"></div>';
  return html;
});
A.revScan = function(id){
  var d = DB.datasources.find(function(x){return x.id===id;});
  UI.toast('正在扫描 '+d.name+' ...', 'info');
  setTimeout(function(){
    document.getElementById('revStep2').innerHTML = UI.card('第二步：选择要导入的表（'+UI.esc(d.name)+'）', UI.tbl({
      id:'t_rev2', rowKey:'n', pageSize:8, searchKeys:['n'], selectable:true,
      data:function(){ return [{n:'user_info', c:8},{n:'order_info', c:12},{n:'product_info', c:7},{n:'coupon_record', c:11}]; },
      cols:[{t:'表名',k:'n',render:function(r){return '<span class="mono">'+r.n+'</span>';}},{t:'字段数',k:'c'}],
      ops:function(){ return ''; }
    }) + '<div style="display:flex;gap:8px"><button class="btn btn-primary" onclick="A.revImport(\''+d.id+'\')">导入生成逻辑模型</button><button class="btn" onclick="UI.toast(\'请先勾选表\',\'warn\')">导入并配置分区</button></div>');
  }, 700);
};
A.revImport = function(dsid){
  var sel = UI.selRows('t_rev2');
  if(!sel.length){ UI.toast('请先勾选要导入的表', 'warn'); return; }
  UI.confirm({title:'导入确认', msg:'确认将选中的 '+sel.length+' 张表反向生成为逻辑模型？', detail:'默认导入至 ODS 层，生成后可调整分层与字段。', onOk:function(){
    sel.forEach(function(t){
      var id = 'MD'+String(DB.models.length+1).padStart(3,'0');
      DB.models.push({id:id, name:t+'（逆向导入）', code:'ods_imported_'+t, layer:'ODS', engine:'Apache Doris', type:'明细表', status:'draft',
        fields:[{n:'id',t:'BIGINT',len:'',pk:true,pkPart:false,cmt:'主键',def:''},{n:'dt',t:'DATE',len:'',pk:false,pkPart:true,cmt:'分区',def:''}],
        version:1, owner:DB.user.name, bizDomain:'公共', updatedAt:'2026-09-12 22:55',
        versions:[{v:1,date:'2026-09-12 22:55',author:DB.user.name,note:'逆向工程导入自 '+dsid, status:'当前版本'}]});
    });
    UI.toast('已导入生成 '+sel.length+' 个逻辑模型（ODS层草稿）', 'success');
    App.go('#/model/list');
  }});
};

/* 模型血缘与影响 */
App.reg('#/model/lineage/:id', '模型血缘与影响', function(p){
  var m = DB.models.find(function(x){return x.id===p.id;});
  if(!m) return '<div class="empty"><span class="e-ico">⌀</span><p>模型不存在，请从模型列表进入</p><a onclick="App.go(\'#/model/list\')">返回列表</a></div>';
  var code = m.code;
  var ups = DB.tableLineage.filter(function(e){return e.to===code;});
  var downs = DB.tableLineage.filter(function(e){return e.from===code;});
  var html = UI.pageHead('<a onclick="App.go(\'#/model/list\')">← 数仓建模</a> / 血缘与影响 - '+code,
    '模型与 ETL 任务、数据血缘关联；模型变更时自动提示影响范围');
  html += UI.card('上游来源（'+ups.length+'）', ups.length? UI.tbl({
    id:'t_up', rowKey:'from', pageSize:5, searchKeys:['from','task'],
    data:function(){ return ups; },
    cols:[{t:'上游表',k:'from',render:function(r){return '<span class="mono">'+r.from+'</span>';}},{t:'产出任务',k:'task'},{t:'所属工作流',k:'wf'}],
    ops:function(r){ return '<a onclick="App.go(\'#/meta/lineage\')">查看全链路血缘</a>'; }}) : '<div class="empty"><span class="e-ico">⌀</span><p>暂无上游（顶层模型或未入任务）</p></div>');
  html += UI.card('下游影响（'+downs.length+'）', downs.length? UI.tbl({
    id:'t_down', rowKey:'to', pageSize:5, searchKeys:['to','task'],
    data:function(){ return downs; },
    cols:[{t:'下游表',k:'to',render:function(r){return '<span class="mono">'+r.to+'</span>';}},{t:'消费任务',k:'task'},{t:'所属工作流',k:'wf'}],
    ops:function(r){ return '<a onclick="A.mdImpact(\''+r.to+'\')">影响分析</a>'; }}) : '<div class="empty"><span class="e-ico">⌀</span><p>暂无下游</p></div>');
  html += UI.card('变更影响模拟', '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>若修改 <b class="mono">'+code+'</b> 的字段定义，将影响下游 <b>'+downs.length+'</b> 个模型、<b>'+downs.length+'</b> 个任务、<b>'+(code==='dwd_order_pay_detail'?2:1)+'</b> 个指标。</span></div>'
    + '<button class="btn btn-primary" onclick="A.mdImpact(\''+code+'\')">查看完整影响分析</button>');
  return html;
});
/* 通用影响分析弹窗：按表名递归追溯下游表/任务/工作流/指标，与血缘分析-影响分析口径一致 */
A.mdImpact = function(code){
  var downs = DB.tableLineage.filter(function(e){return e.from===code;});
  var wfs = {}; downs.forEach(function(e){ wfs[e.wf] = 1; });
  var im = DB.impactExample && DB.impactExample.table===code ? DB.impactExample : null;
  var inds = im? im.downIndicators : DB.indicators.filter(function(i){return i.srcTable===code;}).map(function(i){return {name:i.name, code:i.code};});
  var reports = im? im.reports : ['经营驾驶舱 · 概览'];
  UI.modal({title:'变更影响分析 - '+code, w:'w-xl', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button><button class="btn btn-primary" onclick="UI.closeModal();App.go(\'#/meta/lineage\')">打开血缘全景图</button>', body:
    '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>变更 <b class="mono">'+code+'</b> 结构/口径前，请按「通知负责人 → 调整下游 → 重跑验证」闭环处理。</span></div>'
    + '<div class="grid" style="grid-template-columns:1fr 1fr;gap:12px">'
    + UI.card('受影响下游表（'+downs.length+'）', downs.map(function(e){return '<div class="checker-line"><span>▤</span><b class="mono">'+e.to+'</b><span style="margin-left:auto;color:var(--text-3)">'+e.task+'</span></div>';}).join('')||'<div class="empty" style="padding:16px"><p>无下游</p></div>')
    + UI.card('受影响工作流（'+Object.keys(wfs).length+'）', Object.keys(wfs).map(function(w){return '<div class="checker-line"><span>⑃</span><b>'+w+'</b></div>';}).join('')||'<div class="empty" style="padding:16px"><p>无关联调度</p></div>')
    + UI.card('受影响指标（'+inds.length+'）', inds.map(function(t){return '<div class="checker-line"><span>✦</span><b>'+UI.esc(t.name)+'</b><span style="margin-left:auto;color:var(--text-3)">'+t.code+'</span></div>';}).join('')||'<div class="empty" style="padding:16px"><p>无</p></div>')
    + UI.card('受影响报表（'+reports.length+'）', reports.map(function(r){return '<div class="checker-line"><span>◫</span><b>'+r+'</b></div>';}).join(''))
    + '</div>'});
};
})();
