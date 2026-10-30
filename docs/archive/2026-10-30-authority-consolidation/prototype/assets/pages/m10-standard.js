/* ============================================================
   M10 数据标准（数据元/代码/命名/映射/审批）+ M10i 指标管理
   ============================================================ */
(function(){
/* ---- 数据元标准（三栏工作台：层级目录树 | 规范详情 | 校验与稽核） ---- */
/* 工作台局部状态与演示数据（仅存于本页，不改 data.js） */
var SX = { cur:'DE-003', open:{}, q:'', reports:[], seq:0 };
var SX_EXTRA = [
  {id:'DE-006', cn:'性别', en:'gender', type:'CHAR', len:1, format:'枚举 M/F（GB/T 2261.1）', domain:'公共', desc:'用户性别代码', status:'published', v:1, owner:'王工', updatedAt:'2026-09-01'},
  {id:'DE-007', cn:'机构名称', en:'org_name', type:'VARCHAR', len:100, format:'非空，≤100字符', domain:'公共', desc:'用户所属机构名称', status:'published', v:1, owner:'王工', updatedAt:'2026-08-28'},
  {id:'DE-008', cn:'凭证号', en:'voucher_id', type:'VARCHAR', len:32, format:'V+yyyyMMdd+序号', domain:'财务域', desc:'ERP总账凭证唯一编号', status:'published', v:1, owner:'赵工', updatedAt:'2026-09-02'},
  {id:'DE-009', cn:'支付用户数', en:'pay_user_cnt', type:'BIGINT', len:'-', format:'≥0，按日去重', domain:'交易域', desc:'统计期内支付用户去重数（指标数据元）', status:'published', v:2, owner:'李工', updatedAt:'2026-09-09'},
  {id:'DE-010', cn:'近7天支付金额', en:'pay_amount_7d', type:'DECIMAL', len:'(18,2)', format:'≥0，单位元', domain:'经营域', desc:'滚动7天支付金额汇总（指标数据元）', status:'published', v:1, owner:'赵工', updatedAt:'2026-09-10'}
];
var SX_SPECS = {
  'DE-001':{phys:'user_id BIGINT NOT NULL COMMENT "用户唯一标识"', regex:'^[1-9][0-9]{0,17}$',
    refs:['ods_gdb_biz_user_info.user_id','dwd_order_pay_detail.user_id'], inds:['METRIC_003 支付用户数'],
    issues:[{t:'ODS 源端 ods_gdb_biz_user_info.user_id 存在 214 条 NULL 违例', f:'上游增量时间窗重叠导致重复写入，建议改 merge 幂等写入并对存量补录映射'}],
    sugs:['为 user_id 挂接非空率≥99.9% 质量规则','血缘回溯补齐源头主键生成逻辑']},
  'DE-002':{phys:'phone VARCHAR(20) NOT NULL COMMENT "手机号"', regex:'^1[3-9][0-9]{9}$',
    refs:['ods_gdb_biz_user_info.phone'], inds:[],
    issues:[{t:'正则未覆盖 +86 国际前缀场景，存量约 0.3% 数据带前缀', f:'扩展正则为 ^(\\+86)?1[3-9][0-9]{9}$，存量数据自动清洗去前缀'}],
    sugs:['正则变更走标准 v2 评审','清洗脚本先在测试分区验证后全量执行']},
  'DE-003':{phys:'pay_amount DECIMAL(18,2) NOT NULL COMMENT "支付金额（元）"', regex:'—（值域约束 ≥0）',
    refs:['dwd_order_pay_detail.pay_amount','dws_pay_summary_daily.pay_amount_sum'], inds:['METRIC_001 支付金额','METRIC_005 客单价'],
    issues:[{t:'ads_kpi_report.pay_amount_7d 使用 DECIMAL(16,2)，与标准精度 (18,2) 不一致', f:'生成 DDL 变更：ALTER TABLE ads_kpi_report MODIFY pay_amount_7d DECIMAL(18,2)'}],
    sugs:['下游宽表精度统一为 (18,2)','变更发布后自动触发映射复检']},
  'DE-004':{phys:'pay_channel VARCHAR(20) NOT NULL COMMENT "支付渠道（C-005）"', regex:'^(ALIPAY|WECHAT|UNIONPAY|BANK)$', codeRef:'C-005',
    refs:['dwd_order_pay_detail.pay_channel'], inds:['METRIC_004 渠道支付占比'],
    issues:[{t:'字段注释缺渠道枚举说明（对照码表 C-005），映射检核 SM002 不合规', f:'自动补全注释：枚举 ALIPAY/WECHAT/UNIONPAY/BANK（对照 C-005）'}],
    sugs:['注释变更随模型 v2 发布','发布后复检 SM002 映射项']},
  'DE-005':{phys:'stat_date DATE NOT NULL COMMENT "统计日期"', regex:'^[0-9]{4}-[0-9]{2}-[0-9]{2}$',
    refs:['dws_pay_summary_daily.stat_date','ads_kpi_report.stat_date'], inds:[],
    issues:[{t:'部分汇总表以 STRING 存储日期，与标准类型 DATE 不一致', f:'类型改为 DATE 并按分区重跑历史数据'}],
    sugs:['建模时对 DATE 类字段强制类型约束','批量巡检 STRING 日期字段并生成整改单']},
  'DE-006':{phys:'gender CHAR(1) COMMENT "性别（M/F）"', regex:'^[MF]$', enumVals:[{c:'M',n:'男'},{c:'F',n:'女'}],
    refs:['ods_gdb_biz_user_info.gender'], inds:[],
    issues:[{t:'存在 M/F 与 1/2 两套编码并存，取值域冲突', f:'统一采用 GB/T 2261.1（M/F）编码，已生成映射转换脚本'}],
    sugs:['统一编码后发布标准 v2','对 1/2 存量数据执行一次性转换并复检']},
  'DE-007':{phys:'org_name VARCHAR(100) COMMENT "机构名称"', regex:'—',
    refs:['dim_user.org_name'], inds:[],
    issues:[{t:'dim_user.org_name 字段长度 200 超标准 100（映射检核 SM005 不合规）', f:'截断至 100 字符，或发起标准扩展审批（扩展至 VARCHAR(200)）'}],
    sugs:['优先评估业务上是否存在超长机构名','整改后复检 SM005 映射项']},
  'DE-008':{phys:'voucher_id VARCHAR(32) NOT NULL COMMENT "凭证号"', regex:'^V[0-9]{11,13}$',
    refs:['ods_oracle_gl_voucher.voucher_id','dwd_gl_voucher_detail.voucher_id'], inds:[],
    issues:[{t:'格式 V+日期+序号 未配置正则校验规则，脏数据无法拦截', f:'补充正则 ^V[0-9]{11,13}$ 并挂接质量规则库'}],
    sugs:['在 ODS→DWD 清洗节点增加正则校验算子','对历史凭证做一次全量格式扫描']},
  'DE-009':{phys:'pay_user_cnt BIGINT COMMENT "支付用户数（去重）"', regex:'—（值域约束 ≥0）',
    refs:['dws_pay_summary_daily.pay_user_cnt','ads_kpi_report.pay_user_cnt'], inds:['METRIC_003 支付用户数'],
    issues:[{t:'ads 层与 dws 层对「是否去重」口径存在歧义', f:'按标准口径「成功支付用户按日去重（不含退款）」修正计算逻辑'}],
    sugs:['口径变更走指标审批流','对齐后触发一致性复检']},
  'DE-010':{phys:'pay_amount_7d DECIMAL(18,2) COMMENT "近7天支付金额"', regex:'—（值域约束 ≥0）',
    refs:['ads_kpi_report.pay_amount_7d'], inds:['METRIC_002 近7天支付金额'],
    issues:[{t:'滚动窗口边界未注明（自然日 / 24小时），口径易歧义', f:'在业务口径中明确为自然日滚动 7 天，并对齐 METRIC_002 技术口径'}],
    sugs:['口径说明补充至数据元业务描述','一致性检查纳入每日巡检']},
  'C-006':{issues:[{t:'订单状态存在历史遗留码值 06=已关闭 未纳入标准', f:'码表增补 06=已关闭 并升级 v2 发布'}],
    sugs:['增补后通知引用方更新枚举展示','升级发布后复检 8 处引用']},
  'C-007':{issues:[{t:'码表为草稿状态未发布，引用存在不一致风险', f:'补齐码值后提交发布流程，发布前冻结新增引用'}],
    sugs:['发布前核对币种与财务凭证字段匹配性','发布后自动开放引用并纳入巡检']}
};
var SX_TREE = [
  {n:'基础数据元', g:[
    {d:'用户', items:['DE-001','DE-002','DE-006']},
    {d:'交易', items:['DE-003','DE-004']},
    {d:'财务', items:['DE-008']},
    {d:'公共', items:['DE-005','DE-007']}]},
  {n:'指标数据元', g:[
    {d:'交易', items:['DE-009','DE-010']}]},
  {n:'码表字典', g:[
    {d:'公共', items:['C-003','C-005','C-006','C-007']}]}
];
function sxEl(id){
  return DB.stdElements.find(function(x){return x.id===id;})
    || SX_EXTRA.find(function(x){return x.id===id;})
    || DB.stdCodes.find(function(x){return x.id===id;});
}
function sxSpec(id){ return SX_SPECS[id]||{}; }
function sxNow(){ return now+' '+new Date().toTimeString().slice(0,5); }
function sxTreeData(){
  var covered = {};
  SX_TREE.forEach(function(l1){ l1.g.forEach(function(g){ g.items.forEach(function(id){ covered[id]=1; }); }); });
  var tree = SX_TREE.map(function(l1){ return {n:l1.n, g:l1.g.map(function(g){ return {d:g.d, items:g.items.slice()}; })}; });
  DB.stdElements.concat(SX_EXTRA).forEach(function(e){
    if(covered[e.id]) return;
    var dm = ({'交易域':'交易','财务域':'财务','经营域':'交易'})[e.domain]||'公共';
    var g = tree[0].g.find(function(x){ return x.d===dm; });
    if(g) g.items.push(e.id);
  });
  return tree;
}
function sxTreeHtml(){
  var q = (SX.q||'').trim().toLowerCase(), h = '';
  sxTreeData().forEach(function(l1){
    var ghtml = '', total = 0;
    l1.g.forEach(function(g){
      total += g.items.length;
      var leaves = '';
      g.items.forEach(function(id){
        var e = sxEl(id); if(!e) return;
        if(q && (e.id+' '+(e.cn||'')+' '+(e.en||e.name||'')).toLowerCase().indexOf(q)<0) return;
        var on = SX.cur===id;
        leaves += '<div onclick="A.sxSel(\''+id+'\')" style="display:flex;align-items:center;gap:6px;padding:5px 12px 5px 48px;cursor:pointer;font-size:12px;background:'+(on?'var(--primary-light)':'transparent')+';border-left:'+(on?'2px solid var(--primary)':'2px solid transparent')+'">'
          + '<span class="mono" style="color:'+(on?'var(--primary)':'var(--text)')+';white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+UI.esc(e.en||e.id)+'</span>'
          + '<span style="margin-left:auto;font-size:10.5px;color:var(--text-3);flex-shrink:0">'+UI.esc(e.cn||e.name||'')+'</span></div>';
      });
      if(q && !leaves) return;
      var key2 = l1.n+'/'+g.d, open2 = SX.open[key2]!==false;
      ghtml += '<div style="display:flex;align-items:center;gap:6px;padding:5px 12px 5px 26px;cursor:pointer;font-size:12px;color:var(--text-2)" onclick="A.sxToggle(\''+key2+'\')">'
        + '<span style="color:var(--text-3);font-size:10px;width:10px">'+(open2?'▾':'▸')+'</span><span>'+g.d+'</span>'
        + '<span class="tag tag-outline" style="height:15px;font-size:10px;padding:0 5px;margin-left:auto">'+g.items.length+'</span></div>'
        + '<div style="display:'+(open2?'block':'none')+'">'+leaves+'</div>';
    });
    if(q && !ghtml) return;
    var open1 = SX.open[l1.n]!==false;
    h += '<div style="display:flex;align-items:center;gap:6px;padding:7px 12px;cursor:pointer;font-weight:600;font-size:12.5px;color:var(--text)" onclick="A.sxToggle(\''+l1.n+'\')">'
      + '<span style="color:var(--text-3);font-size:10px;width:10px">'+(open1?'▾':'▸')+'</span><span>'+l1.n+'</span>'
      + '<span class="tag tag-gray" style="height:16px;font-size:10px;padding:0 6px;margin-left:auto">'+total+'</span></div>'
      + '<div style="display:'+(open1?'block':'none')+'">'+ghtml+'</div>';
  });
  if(!h) h = '<div class="lock-tip" style="margin:10px 12px">未找到匹配的数据元 / 码表</div>';
  return h;
}
function sxEnumTable(vals){
  if(!vals || !vals.length) return '<div class="lock-tip" style="margin-top:0">无枚举值，按值域/正则约束取值</div>';
  return '<table style="width:100%;border-collapse:collapse;font-size:12px">'
    + '<tr style="color:var(--text-3)"><td style="padding:4px 8px;border-bottom:1px solid var(--border);width:42%">码值</td><td style="padding:4px 8px;border-bottom:1px solid var(--border)">含义</td></tr>'
    + vals.map(function(v){ return '<tr><td style="padding:4px 8px;border-bottom:1px solid var(--border)"><span class="mono">'+UI.esc(v.c)+'</span></td><td style="padding:4px 8px;border-bottom:1px solid var(--border)">'+UI.esc(v.n)+'</td></tr>'; }).join('')
    + '</table>';
}
function sxRefs(maps, sp){
  var h = '';
  maps.forEach(function(m){
    h += '<div class="checker-line '+(m.result==='pass'?'ok':'err')+'" style="margin-bottom:6px"><span>'+(m.result==='pass'?'✓':'✗')+'</span><span class="mono" style="font-size:11.5px">'+m.table+'.'+m.field+'</span><span style="margin-left:auto;font-size:11px;color:var(--text-3)">'+UI.esc(m.diff)+'</span></div>';
  });
  var inds = sp.inds||[], refs = sp.refs||[];
  if(inds.length) h += '<div style="margin:6px 0 4px;font-size:11px;color:var(--text-3)">指标引用</div><div>'+inds.map(function(x){ return '<span class="tag tag-purple" style="margin:0 4px 4px 0">'+UI.esc(x)+'</span>'; }).join('')+'</div>';
  if(refs.length) h += '<div style="margin:6px 0 4px;font-size:11px;color:var(--text-3)">其他表引用</div><div>'+refs.map(function(x){ return '<span class="tag tag-outline mono" style="margin:0 4px 4px 0;font-size:11px">'+UI.esc(x)+'</span>'; }).join('')+'</div>';
  if(!h) return '<div class="lock-tip" style="margin-top:0">暂无字段映射与指标引用</div>';
  return h;
}
function sxMidHtml(){
  var e = sxEl(SX.cur);
  if(!e) return '<div style="padding:60px 20px;text-align:center;color:var(--text-3);font-size:12.5px">请在左侧层级目录中选择数据元或码表</div>';
  var sp = sxSpec(SX.cur), isCode = SX.cur.indexOf('C-')===0, h = '';
  h += '<div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
    + '<b style="font-size:15px">'+(e.cn||e.name)+'</b>'
    + '<span class="mono" style="font-size:12px;color:var(--text-3)">'+e.id+' · '+UI.esc(e.en||e.name||'')+'</span>'
    + st(e.status)+'<span style="flex:1"></span>'
    + '<button class="btn btn-sm btn-primary" onclick="A.sxEdit()">编辑规范</button></div>';
  h += '<div style="padding:12px 14px">';
  if(isCode){
    h += UI.card('命名规范', UI.desc([['码表编码', e.id],['码表名称', e.name],['状态', st(e.status)],['引用计数', (e.used||0)+' 处']])
      + '<div class="lock-tip">码表编码遵循 C-XXX 编号规则；码值需在「代码标准」页维护并发布后方可被模型与质量规则引用。</div>');
    h += '<div style="height:12px"></div>';
    h += UI.card('取值规范', '<div style="font-size:12px;color:var(--text-2);margin-bottom:6px">枚举码值（'+e.values.length+' 项）</div>'+sxEnumTable(e.values));
    h += '<div style="height:12px"></div>';
    h += UI.card('引用情况', sxRefs(DB.stdMappings.filter(function(m){ return m.stdId===e.id; }), sp));
  } else {
    var nr = DB.namingRules[4];
    h += UI.card('命名规范', UI.desc([['编码', e.id],['中文名', e.cn],['英文名','<span class="mono">'+UI.esc(e.en)+'</span>'],
        ['物理名建议','<span class="mono" style="font-size:11.5px">'+UI.esc(sp.phys||'-')+'</span>'],
        ['数据类型','<span class="mono">'+e.type+'</span>'],
        ['长度/精度', e.len&&e.len!=='-'? '<span class="mono">'+e.len+'</span>':'-']])
      + '<div class="lock-tip">命名规则说明：字段命名须符合 '+nr.scope+'「'+UI.esc(nr.pattern)+'」，参考示例 '+UI.esc(nr.eg)+'；表命名遵循各分层规范（NR-01~04），建模保存与任务发布时自动拦截。</div>');
    h += '<div style="height:12px"></div>';
    var codeRef = '—';
    if(sp.codeRef){ var c = DB.stdCodes.find(function(x){ return x.id===sp.codeRef; });
      codeRef = c? '<a onclick="A.sxSel(\''+c.id+'\')"><span class="mono">'+c.id+'</span> '+c.name+'</a>' : '—'; }
    h += UI.card('取值规范', UI.desc([['值域/格式约束', UI.esc(e.format||'-')],['码表引用', codeRef],
        ['校验正则','<span class="mono" style="font-size:11.5px">'+UI.esc(sp.regex||'—')+'</span>']])
      + (sp.enumVals? '<div style="margin-top:8px"><div style="font-size:12px;color:var(--text-2);margin-bottom:6px">枚举值</div>'+sxEnumTable(sp.enumVals)+'</div>' : ''));
    h += '<div style="height:12px"></div>';
    h += UI.card('引用情况', sxRefs(DB.stdMappings.filter(function(m){ return m.stdId===e.id; }), sp));
  }
  h += '</div>';
  return h;
}
function sxReportFor(id){
  var e = sxEl(id), sp = sxSpec(id), isCode = id.indexOf('C-')===0;
  var pass = isCode? [
      '码表 '+e.id+' 已登记，当前状态：'+(e.status==='published'?'已发布':'草稿'),
      '码值含义无重复、无空值',
      '引用计数有效（'+(e.used||0)+' 处）'
    ] : [
      '英文名符合 snake_case 字段命名规范（NR-05）',
      '类型/长度定义与模型映射字段一致',
      '主题域归属正确：'+e.domain
    ];
  return {id:'R'+(++SX.seq), el:e.id+' '+(e.cn||e.name), time:sxNow(),
    pass:pass,
    issues:(sp.issues||[]).map(function(x){ return {t:x.t, f:x.f, st:'open'}; }),
    sugs:(sp.sugs||[]).slice()};
}
function sxReportCard(r){
  var h = '<div style="border:1px solid var(--border);border-radius:8px;padding:9px 10px;margin-bottom:10px;background:#fff">'
    + '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><b style="font-size:12px">'+r.id+'</b>'
    + '<span style="font-size:11px;color:var(--text-3)">'+UI.esc(r.el)+'</span>'
    + '<span class="tag '+(r.issues.length?'tag-orange':'tag-green')+'" style="height:16px;font-size:10px;margin-left:auto">通过'+r.pass.length+' · 问题'+r.issues.length+'</span></div>'
    + '<div style="font-size:10.5px;color:var(--text-3);margin:3px 0 7px">'+r.time+'</div>';
  r.pass.forEach(function(p){ h += '<div class="checker-line ok" style="margin-bottom:5px"><span>✓</span><span style="font-size:11.5px">'+UI.esc(p)+'</span></div>'; });
  if(r.issues.length) h += '<div style="font-size:11px;color:var(--text-2);margin:7px 0 5px;font-weight:600">问题项</div>';
  r.issues.forEach(function(it, i){
    h += '<div class="checker-line err" style="align-items:flex-start;margin-bottom:5px"><span>'+(it.st==='verified'?'✓':'✗')+'</span><div style="flex:1">'
      + '<div style="font-size:11.5px">'+UI.esc(it.t)+'</div>'
      + '<div style="font-size:10.5px;color:var(--text-3);margin-top:2px">整改建议：'+UI.esc(it.f)+'</div>';
    if(it.st==='fixed') h += '<div style="font-size:11px;margin-top:4px"><span class="tag tag-orange" style="height:16px;font-size:10px">已自动修复·待人工核验</span> <a onclick="A.sxVerify(\''+r.id+'\','+i+')">人工核验</a></div>';
    else if(it.st==='verified') h += '<div style="font-size:11px;margin-top:4px"><span class="tag tag-green" style="height:16px;font-size:10px">已核验关闭 ✓</span></div>';
    else h += '<div style="font-size:11px;margin-top:4px"><a onclick="A.sxFix(\''+r.id+'\','+i+')">✦ 一键 AI 修复</a></div>';
    h += '</div></div>';
  });
  if(r.sugs.length) h += '<div style="font-size:11px;color:var(--text-2);margin:7px 0 4px;font-weight:600">整改建议</div>'
    + '<div class="lock-tip" style="margin-top:0"><ol style="margin:0;padding-left:16px">'+r.sugs.map(function(s){ return '<li style="margin:2px 0">'+UI.esc(s)+'</li>'; }).join('')+'</ol></div>';
  return h+'</div>';
}
function sxRightHtml(){
  var e = sxEl(SX.cur), h = '';
  h += '<div style="padding:12px 14px;border-bottom:1px solid var(--border)">'
    + '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><b style="font-size:13px">校验与稽核</b>'
    + (e? '<span class="tag tag-blue" style="height:17px;font-size:10px">'+UI.esc(e.cn||e.name)+'</span>' : '')+'</div>'
    + '<div style="display:flex;flex-direction:column;gap:6px;margin-top:9px">'
    + '<button class="btn btn-primary" style="width:100%" onclick="A.sxCheck()">▶ 校验当前元</button>'
    + '<button class="btn" style="width:100%" onclick="A.sxAudit()">✦ AI 全量稽核</button>'
    + '<button class="btn" style="width:100%" onclick="A.sxTask()">⚡ 触发全局校验任务</button>'
    + '</div></div><div style="padding:10px 14px">'
    + '<div style="font-size:12px;font-weight:600;color:var(--text-2);margin:2px 0 8px">稽核结果（'+SX.reports.length+'）</div>';
  if(!SX.reports.length) h += '<div class="lock-tip">暂无稽核报告。点击上方按钮发起校验 / 稽核，报告将在此逐条追加；问题项支持「一键 AI 修复 → 人工核验」整改闭环。</div>';
  h += SX.reports.map(sxReportCard).join('')+'</div>';
  return h;
}
function sxRenderTree(){ var el = document.getElementById('sxTree'); if(el) el.innerHTML = sxTreeHtml(); }
function sxRenderMid(){ var el = document.getElementById('sxMid'); if(el) el.innerHTML = sxMidHtml(); }
function sxRenderRight(){ var el = document.getElementById('sxRight'); if(el) el.innerHTML = sxRightHtml(); }
App.reg('#/std/element', '数据元标准', function(){
  var html = UI.pageHead('数据元标准',
    '三栏工作台：左侧层级目录树（基础/指标/码表 × 主题域），中栏命名规范与取值规范详情，右栏校验与稽核（AI 修复 → 人工核验闭环）',
    '<button class="btn btn-primary" onclick="A.deCreate()">+ 新建数据元</button>'
    +'<button class="btn" onclick="App.go(\'#/std/mapping\')">查看映射合规</button>');
  html += '<div style="display:grid;grid-template-columns:230px 1fr 300px;gap:0;height:640px;background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden;box-shadow:var(--shadow)">'
    + '<div style="display:flex;flex-direction:column;border-right:1px solid var(--border);background:#fafbfd;min-height:0">'
    + '<div style="padding:10px 10px 8px;border-bottom:1px solid var(--border)"><input class="inp" style="height:30px;font-size:12px" placeholder="搜索数据元 / 码表…" value="'+UI.esc(SX.q||'')+'" oninput="A.sxFilter(this.value)"></div>'
    + '<div id="sxTree" style="flex:1;min-height:0;overflow-y:auto">'+sxTreeHtml()+'</div></div>'
    + '<div id="sxMid" style="overflow-y:auto;min-height:0">'+sxMidHtml()+'</div>'
    + '<div id="sxRight" style="overflow-y:auto;min-height:0;border-left:1px solid var(--border);background:#fafbfd">'+sxRightHtml()+'</div>'
    + '</div>';
  return html;
});
A.sxToggle = function(key){ SX.open[key] = SX.open[key]===false; sxRenderTree(); };
A.sxFilter = function(q){ SX.q = q; sxRenderTree(); };
A.sxSel = function(id){ SX.cur = id; sxRenderTree(); sxRenderMid(); sxRenderRight(); };
A.sxCheck = function(){
  var e = sxEl(SX.cur);
  if(!e){ UI.toast('请先在左侧选择数据元', 'warn'); return; }
  UI.toast('正在校验「'+(e.cn||e.name)+'」：命名规范 / 类型精度 / 取值域 / 码表引用 ...', 'info');
  setTimeout(function(){
    var r = sxReportFor(SX.cur);
    SX.reports.unshift(r); sxRenderRight();
    UI.toast('校验完成：通过 '+r.pass.length+' 项，问题 '+r.issues.length+' 项，报告 '+r.id+' 已生成', r.issues.length?'warn':'success');
  }, 900);
};
A.sxAudit = function(){
  var total = DB.stdElements.length + SX_EXTRA.length;
  AI.show('数据标准全量稽核报告（'+now+'）：\n· 数据元 '+total+' 项 + 码表 '+DB.stdCodes.length+' 部，抽样 128 个字段\n· 命名符合标准 119 项（93.0%）\n· 取值域冲突 1 项：gender 存在 M/F 与 1/2 两套编码 → 建议统一 GB/T 2261.1\n· 长度越标 1 项：dim_user.org_name 200 超标准 100\n· 未发布码表 1 部：C-007 币种（草稿）\n\n问题项已在右侧「稽核结果」生成报告卡，可逐项「一键 AI 修复」→「人工核验」闭环。');
  SX.reports.unshift({id:'R'+(++SX.seq), el:'全量稽核（数据元 '+total+' / 码表 '+DB.stdCodes.length+'）', time:sxNow(),
    pass:['命名规范符合率 93.0%（抽样 128 字段，119 项符合 NR-05）','码表引用有效率 96%，字典枚举无冲突','主题域归属完整率 100%'],
    issues:[
      {t:'DE-006 gender：存在 M/F 与 1/2 两套编码并存，取值域冲突', f:'统一采用 GB/T 2261.1（M/F）编码，已生成映射转换脚本', st:'open'},
      {t:'DE-007 org_name：dim_user 字段长度 200 超标准 100', f:'截断至 100 字符或发起标准扩展审批（映射页 SM005 已记录）', st:'open'},
      {t:'C-007 币种：码表为草稿状态未发布，存在引用风险', f:'补齐码值后提交发布流程，发布前冻结新增引用', st:'open'}
    ],
    sugs:['按优先级下发整改工单：取值域冲突 > 长度越标 > 码表未发布','整改完成后自动触发复检，结果回写本报告']});
  sxRenderRight();
};
A.sxTask = function(){
  UI.confirm({title:'触发全局校验任务', msg:'对全部数据元与码表发起一轮标准校验任务？', detail:'任务异步执行四类检核：命名规范 / 类型精度 / 取值域 / 码表引用，完成后自动生成报告。', onOk:function(){
    UI.toast('全局校验任务已提交（TASK-STD-'+(100+SX.seq)+'），执行中...', 'info');
    setTimeout(function(){
      var r = {id:'R'+(++SX.seq), el:'全局校验任务首轮结果', time:sxNow(),
        pass:['命名规范批量检核完成：119/128 符合','码表枚举引用批量检核完成：无未知码值'],
        issues:[
          {t:'批量扫描发现 6 个字段未挂接任何数据元标准（手机号/证件号等）', f:'已推荐对应数据元，可在「映射合规」页一键挂接', st:'open'},
          {t:'DWD 层 2 个字段类型与标准不一致（DECIMAL(16,2) vs (18,2)）', f:'生成 DDL 变更工单，整改后自动复检', st:'open'}
        ],
        sugs:['为未挂接字段制定标准映射补录计划','将本任务固化为每日凌晨定时校验']};
      SX.reports.unshift(r); sxRenderRight();
      UI.toast('全局校验完成，报告 '+r.id+' 已生成', 'warn');
    }, 1200);
  }});
};
A.sxFix = function(rid, i){
  var r = SX.reports.find(function(x){ return x.id===rid; }); if(!r) return;
  var it = r.issues[i]; if(!it || it.st!=='open') return;
  it.st = 'fixed'; sxRenderRight();
  UI.toast('AI 已自动修复并生成变更记录，状态变更为「待人工核验」', 'success');
};
A.sxVerify = function(rid, i){
  var r = SX.reports.find(function(x){ return x.id===rid; }); if(!r) return;
  var it = r.issues[i]; if(!it || it.st!=='fixed') return;
  it.st = 'verified'; sxRenderRight();
  UI.toast('人工核验通过，问题已核验关闭，整改闭环完成 ✓', 'success');
};
A.sxEdit = function(){
  var e = sxEl(SX.cur); if(!e) return;
  if(SX.cur.indexOf('C-')===0){
    UI.drawer({title:'编辑码表规范 - '+e.name, body:
      '<div class="form-grid">'+UI.fInput('码表名称', 'sxe_name', {value:e.name, req:true})+'</div>'
      +'<div class="lock-tip">码值请在「代码标准」页的码值维护中调整，此处修改名称保存后即时生效。</div>',
      onOk:function(){ var n = UI.val('sxe_name'); if(!n){ UI.toast('请填写名称', 'warn'); return false; }
        e.name = n; sxRenderMid(); UI.toast('码表规范已保存', 'success'); }});
    return;
  }
  UI.drawer({title:'编辑规范 - '+e.cn, w:'w-lg', body:A.deFormFields(e), onOk:function(){
    Object.assign(e, {cn:UI.val('de_cn'), en:UI.val('de_en'), type:UI.val('de_type'), len:UI.val('de_len'), format:UI.val('de_format'), domain:UI.val('de_domain'), desc:UI.val('de_desc'), updatedAt:now});
    sxRenderMid(); sxRenderTree();
    UI.toast('规范已保存（变更需重新提交评审）', 'success');
  }});
};
A.deFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('中文名', 'de_cn', {value:d.cn, req:true})
    + UI.fInput('英文名（snake_case）', 'de_en', {value:d.en, req:true, ph:'如：pay_amount'})
    + UI.fSelect('数据类型', 'de_type', ['BIGINT','DECIMAL','VARCHAR','CHAR','DATE','DATETIME','TINYINT','TEXT'], {value:d.type||'VARCHAR'})
    + UI.fInput('长度/精度', 'de_len', {value:d.len, ph:'如：(18,2) 或 20'})
    + UI.fInput('格式约束', 'de_format', {value:d.format, ph:'如：≥0，单位元', full:true})
    + UI.fSelect('主题域', 'de_domain', DB.bizDomains.map(function(d){return d.name;}), {value:d.domain||'公共'})
    + UI.fTextarea('业务描述', 'de_desc', {value:d.desc, rows:2, full:true})
    + '</div>';
};
A.deCreate = function(){
  UI.drawer({title:'新建数据元', w:'w-lg', body:A.deFormFields({}), onOk:function(){
    var cn = UI.val('de_cn');
    if(!cn||!UI.val('de_en')){ UI.toast('请填写中英文名', 'warn'); return false; }
    var maxId = Math.max.apply(null, DB.stdElements.concat(SX_EXTRA).map(function(x){ return parseInt(x.id.slice(3),10)||0; }));
    DB.stdElements.push({id:'DE-'+String(maxId+1).padStart(3,'0'), cn:cn, en:UI.val('de_en'), type:UI.val('de_type'), len:UI.val('de_len')||'-', format:UI.val('de_format'), domain:UI.val('de_domain'), desc:UI.val('de_desc'), status:'draft', v:1, owner:DB.user.name, updatedAt:now});
    UI.toast('数据元已创建（草稿），可在左侧目录树查看', 'success');
    sxRenderTree(); sxRenderRight();
  }});
};

/* ---- 代码标准 ---- */
App.reg('#/std/code', '代码标准', function(){
  var html = UI.pageHead('代码标准',
    '枚举代码统一管理：码值 / 含义 / 引用计数，供建模字段约束与质量枚举检核使用',
    '<button class="btn btn-primary" onclick="A.cstdCreate()">+ 新建代码标准</button>');
  html += UI.card('代码标准列表', UI.tbl({
    id:'t_cstd', rowKey:'id', pageSize:8, searchKeys:['id','name'], searchPh:'搜索代码标准',
    filters:[{k:'status', label:'状态', options:[{v:'draft',t:'草稿'},{v:'published',t:'已发布'}]}],
    data:function(){ return DB.stdCodes; },
    cols:[
      {t:'标准', k:'name', render:function(r){return '<b>'+r.name+'</b><div style="font-size:11px;color:var(--text-3)">'+r.id+'</div>';}},
      {t:'码值', render:function(r){return r.values.map(function(v){return '<span class="tag tag-outline" style="margin:1px 3px 1px 0">'+v.c+'='+v.n+'</span>';}).join('');}},
      {t:'引用', k:'used', render:function(r){return r.used? '<a onclick="A.cstdUsed(\''+r.id+'\')">'+r.used+' 处</a>':'<span style="color:var(--text-3)">未引用</span>';}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      return '<a onclick="A.cstdValues(\''+r.id+'\')">码值维护</a>'
        +'<a onclick="A.cstdEdit(\''+r.id+'\')">编辑</a>'
        +(r.status==='draft'? '<a onclick="A.cstdPublish(\''+r.id+'\')">发布</a>':'<a onclick="UI.toggleStatus(DB.stdCodes.find(function(x){return x.id===\''+r.id+'\'}),function(){})">停用</a>')
        +'<a class="danger" onclick="A.cstdDel(\''+r.id+'\')">删除</a>';
    }}));
  return html;
});
A.cstdFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('标准名称', 'cs_name', {value:d.name, req:true, ph:'如：支付渠道'})
    + '</div>';
};
A.cstdCreate = function(){
  UI.drawer({title:'新建代码标准', body:A.cstdFormFields({}), footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.cstdSave()">保存（草稿）</button>', onOk:function(){
    var name = UI.val('cs_name');
    if(!name){ UI.toast('请填写名称', 'warn'); return false; }
    DB.stdCodes.push({id:'C-'+String(DB.stdCodes.length+7).padStart(3,'0'), name:name, values:[], status:'draft', used:0});
    UI.toast('代码标准已创建，请维护码值', 'success');
  }});
};
A.cstdSave = A.cstdCreate;
A.cstdEdit = function(id){ var d = DB.stdCodes.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑代码标准', body:A.cstdFormFields(d), onOk:function(){ d.name = UI.val('cs_name'); UI.toast('已保存', 'success'); }}); };
A.cstdValues = function(id){
  var d = DB.stdCodes.find(function(x){return x.id===id;});
  UI.drawer({title:'码值维护 - '+d.name, w:'w-md', body:
    '<div id="csValsBox">'+d.values.map(function(v,i){
      return '<div style="display:flex;gap:8px;margin-bottom:8px"><input class="inp" style="flex:0 0 110px" placeholder="码值" value="'+UI.esc(v.c)+'" onchange="A._csVal('+i+',\'c\',this.value)"><input class="inp" style="flex:1" placeholder="含义" value="'+UI.esc(v.n)+'" onchange="A._csVal('+i+',\'n\',this.value)"><button class="btn btn-sm" onclick="A._csDel('+i+')">删</button></div>';
    }).join('')+'</div><button class="btn btn-sm" onclick="A._csAdd()">+ 增加码值</button>',
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A._csSave(\''+id+'\')">保存码值</button>',
    onMount:function(){ A._csTmp = JSON.parse(JSON.stringify(d.values)); }});
};
A._csTmp = [];
A._csVal = function(i,k,v){ A._csTmp[i][k]=v; };
A._csDel = function(i){ A._csTmp.splice(i,1); var d=UI._drawerCur; UI.closeDrawer(); };
A._csAdd = function(){ A._csTmp.push({c:'',n:''}); UI.closeDrawer(); A.cstdValuesRedraw(); };
A.cstdValuesRedraw = function(){};
A._csSave = function(id){
  var d = DB.stdCodes.find(function(x){return x.id===id;});
  var box = document.querySelectorAll('#csValsBox input');
  var vals = [];
  for(var i=0;i<box.length;i+=2){ if(box[i].value.trim()) vals.push({c:box[i].value.trim(), n:box[i+1].value.trim()}); }
  d.values = vals; UI.toast('码值已保存（'+vals.length+' 项）', 'success');
};
A.cstdPublish = function(id){
  var d = DB.stdCodes.find(function(x){return x.id===id;});
  if(!d.values.length){ UI.toast('请先维护码值再发布', 'warn'); return; }
  UI.confirm({title:'发布代码标准', msg:'发布「'+d.name+'」？', detail:'发布后可被建模与质量规则引用。', onOk:function(){ d.status='published'; UI.toast('「'+d.name+'」已发布', 'success'); App.resolve(); }});
};
A.cstdUsed = function(id){
  var d = DB.stdCodes.find(function(x){return x.id===id;});
  UI.modal({title:'引用明细 - '+d.name, w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.tbl({id:'t_csused', rowKey:'id', pageSize:6, searchKeys:['name'], data:function(){
      return DB.models.filter(function(m){return m.fields.some(function(f){return f.cmt && f.cmt.indexOf(d.name)>=0;});}).map(function(m,i){return {id:m.id, name:m.code+'.'+m.name, layer:m.layer};});},
      cols:[{t:'模型.表', k:'name'},{t:'分层', k:'layer'},{t:'操作', render:function(){return '<a onclick="UI.closeModal();App.go(\'#/model/list\')">查看模型</a>';}}], ops:null})});
};
A.cstdDel = function(id){
  var d = DB.stdCodes.find(function(x){return x.id===id;});
  if(d.used>0){ UI.confirm({title:'无法删除', danger:true, msg:'「'+d.name+'」已被 '+d.used+' 处引用', detail:'请先解除引用后再删除。'}); }
  else UI.delRow(DB.stdCodes, 'id', id, d.name);
};

/* ---- 命名规范 ---- */
App.reg('#/std/naming', '命名规范', function(){
  var html = UI.pageHead('命名规范',
    '表/字段/任务命名规范管理，支持在线校验（正则匹配），建模保存与任务发布时自动拦截不规范命名');
  html += '<div class="grid" style="grid-template-columns:1.5fr 1fr;gap:16px;align-items:flex-start">';
  html += UI.card('规范列表', UI.tbl({
    id:'t_nr', rowKey:'id', pageSize:8, searchKeys:['id','scope','desc'], searchPh:'搜索规范',
    data:function(){ return DB.namingRules; },
    cols:[
      {t:'适用范围', k:'scope'},
      {t:'正则/规则', render:function(r){return '<span class="mono" style="font-size:11.5px">'+UI.esc(r.pattern)+'</span>';}},
      {t:'示例', k:'eg', render:function(r){return '<span class="mono" style="font-size:11.5px;color:var(--success)">'+r.eg+'</span>';}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){ return '<a onclick="A.nrTest(\''+r.id+'\')">校验示例</a><a onclick="A.nrEdit(\''+r.id+'\')">编辑</a>'; }}));
  html += UI.card('命名校验工具', '<div class="form-grid">'
    + UI.fSelect('校验类型', 'nt_type', [{v:'表命名-Ods',t:'ODS表名'},{v:'表命名-Dwd',t:'DWD表名'},{v:'表命名-Dws',t:'DWS表名'},{v:'表命名-Ads',t:'ADS表名'},{v:'字段命名',t:'字段名'},{v:'任务命名',t:'任务名'}], {})
    + UI.fInput('待校验名称', 'nt_name', {ph:'如：dwd_order_pay_detail', full:true})
    + '</div><button class="btn btn-primary" onclick="A.nrRun()">校验</button><div id="ntResult" style="margin-top:10px"></div>');
  html += '</div>';
  return html;
});
A.nrEdit = function(id){
  var d = DB.namingRules.find(function(x){return x.id===id;});
  UI.drawer({title:'编辑命名规范 - '+d.scope, body:
    UI.fInput('适用范围', 'nr_scope', {value:d.scope, req:true})
    + UI.fInput('正则/规则', 'nr_pattern', {value:d.pattern, full:true, mono:1})
    + UI.fInput('示例', 'nr_eg', {value:d.eg})
    + UI.fTextarea('说明', 'nr_desc', {value:d.desc, rows:2}),
    onOk:function(){ Object.assign(d, {scope:UI.val('nr_scope'), pattern:UI.val('nr_pattern'), eg:UI.val('nr_eg'), desc:UI.val('nr_desc')}); UI.toast('命名规范已保存', 'success'); }});
};
A.nrTest = function(id){
  var d = DB.namingRules.find(function(x){return x.id===id;});
  UI.val && (document.getElementById('nt_type') ? document.getElementById('nt_type').value = d.scope : null);
  if(document.getElementById('nt_name')) document.getElementById('nt_name').value = d.eg;
  A.nrRun();
};
A.nrRun = function(){
  var name = UI.val('nt_name'), scope = UI.val('nt_type');
  if(!name){ UI.toast('请输入待校验名称', 'warn'); return; }
  var rule = DB.namingRules.find(function(r){return r.scope===scope;});
  var ok = true, detail = '';
  if(scope==='表命名-Ods') ok = /^ods_[a-z0-9]+_[a-z0-9_]+$/.test(name);
  else if(scope==='表命名-Dwd') ok = /^dwd_[a-z0-9]+_[a-z0-9_]+$/.test(name);
  else if(scope==='表命名-Dws') ok = /^dws_[a-z0-9]+_[a-z0-9_]+$/.test(name);
  else if(scope==='表命名-Ads') ok = /^ads_[a-z0-9]+_[a-z0-9_]+$/.test(name);
  else if(scope==='字段命名') ok = /^[a-z][a-z0-9_]*$/.test(name);
  else if(scope==='任务命名') ok = /^(etl|sync)_[a-z0-9_]+$/.test(name);
  if(!rule){ document.getElementById('ntResult').innerHTML = '<div class="checker-line err"><span>✗</span>未找到适用规范</div>'; return; }
  document.getElementById('ntResult').innerHTML = '<div class="checker-line '+(ok?'ok':'err')+'"><span>'+(ok?'✓':'✗')+'</span><div><b>'+(ok?'符合规范':'不符合规范')+'</b> · '+UI.esc(rule.pattern)+(ok?'':'<div style="font-size:11px;color:var(--text-3);margin-top:3px">参考示例：'+rule.eg+'</div>')+'</div></div>';
};

/* ---- 标准映射与合规 ---- */
App.reg('#/std/mapping', '标准映射与合规', function(){
  var pass = DB.stdMappings.filter(function(m){return m.result==='pass';}).length;
  var html = UI.pageHead('标准映射与合规',
    '模型字段与数据标准自动映射检核：'+DB.stdMappings.length+' 项检核，通过 '+pass+' 项；不合规项需整改后复检',
    '<button class="btn btn-primary" onclick="A.smRunAll()">▶ 全量检核</button>'
    +'<button class="btn" onclick="A.smCreate()">+ 新增映射检核</button>');
  html += '<div class="grid grid-3" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#1668dc">⌇</span><div><div class="stat-num">'+DB.stdMappings.length+'</div><div class="stat-label">映射检核总数</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+pass+'</div><div class="stat-label">合规通过</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#e5484d">✗</span><div><div class="stat-num">'+(DB.stdMappings.length-pass)+'</div><div class="stat-label">不合规待整改</div></div></div></div>';
  html += UI.card('映射检核明细', UI.tbl({
    id:'t_sm', rowKey:'id', pageSize:8, searchKeys:['table','field','stdName'], searchPh:'搜索表/字段/标准',
    filters:[{k:'result', label:'结果', options:[{v:'pass',t:'合规'},{v:'fail',t:'不合规'}]}],
    data:function(){ return DB.stdMappings; },
    cols:[
      {t:'模型字段', render:function(r){return '<span class="mono"><b>'+r.table+'.'+r.field+'</b></span>';}},
      {t:'关联标准', render:function(r){return '<a onclick="App.go(\'#/std/element\')">'+r.stdId+' '+r.stdName+'</a>';}},
      {t:'检核结果', k:'result', render:function(r){return st(r.result==='pass'?'pass':'reject');}},
      {t:'差异说明', k:'diff'},
      {t:'检核时间', k:'checkedAt'}
    ],
    ops:function(r){
      return '<a onclick="A.smFix(\''+r.id+'\')">整改</a><a onclick="A.smRecheck(\''+r.id+'\')">复检</a>';
    }}));
  return html;
});
A.smRunAll = function(){
  UI.toast('正在执行全量映射检核（'+DB.stdMappings.length+' 项）...', 'info');
  setTimeout(function(){
    DB.stdMappings.forEach(function(m){ m.checkedAt = now+' 22:52'; });
    var f = DB.stdMappings.filter(function(m){return m.result==='fail';}).length;
    UI.toast('检核完成：合规 '+(DB.stdMappings.length-f)+' 项，不合规 '+f+' 项（已生成整改工单）', f?'warn':'success'); App.resolve();
  }, 1000);
};
A.smCreate = function(){
  UI.drawer({title:'新增映射检核', w:'w-lg', body:
    UI.fSelect('模型表', 'sm_table', DB.models.map(function(m){return {v:m.code,t:m.code};}), {})
    + UI.fInput('字段名', 'sm_field', {req:true, ph:'如：pay_channel'})
    + UI.fSelect('关联标准', 'sm_std', DB.stdElements.map(function(s){return {v:s.id,t:s.id+' '+s.cn};}), {})
    + '<div class="lock-tip">保存后立即执行一次映射检核（类型/长度/格式约束比对）。</div>',
    onOk:function(){
      var field = UI.val('sm_field');
      if(!field){ UI.toast('请填写字段名', 'warn'); return false; }
      var stdId = UI.val('sm_std');
      var std = DB.stdElements.find(function(s){return s.id===stdId;});
      DB.stdMappings.unshift({id:'SM'+String(DB.stdMappings.length+1).padStart(3,'0'), table:UI.val('sm_table'), field:field, stdId:stdId, stdName:std.cn, result:'pass', diff:'类型/精度一致', checkedAt:now+' 22:53'});
      UI.toast('映射检核已创建并通过', 'success');
    }});
};
A.smFix = function(id){
  var m = DB.stdMappings.find(function(x){return x.id===id;});
  UI.drawer({title:'整改 - '+m.table+'.'+m.field, w:'w-lg', body:
    '<div class="banner banner-warn"><span class="b-ico">⚠</span><span>差异：'+UI.esc(m.diff)+'</span></div>'
    + UI.fRadio('整改方式', 'sm_way', [{v:'alter',t:'调整模型字段（生成DDL变更）'},{v:'extend',t:'扩展标准（走标准变更审批）'},{v:'ignore',t:'豁免（记录理由，审计留痕）'}], 'alter')
    + UI.fTextarea('整改说明', 'sm_note', {rows:2, ph:'说明整改内容与影响'}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.smFixSave(\''+id+'\')">提交整改</button>'});
};
A.smFixSave = function(id){
  var m = DB.stdMappings.find(function(x){return x.id===id;});
  var way = UI.radioVal('sm_way','alter');
  if(!UI.val('sm_note')){ UI.toast('请填写整改说明', 'warn'); return; }
  if(way==='extend'){
    DB.stdApprovals.unshift({id:'SA'+now.replace(/-/g,'')+'-0'+(DB.stdApprovals.length+2), type:'数据元标准', target:'扩展标准 '+m.stdId+'（整改触发）', proposer:DB.user.name, submitAt:now+' 22:54', flow:['起草','评审','发布'], current:1, status:'review', opinion:''});
    UI.toast('已发起标准变更审批，审批通过后复检', 'info');
  } else if(way==='ignore'){
    m.result='pass'; m.diff='豁免：'+UI.val('sm_note'); UI.toast('已豁免并留痕', 'info');
  } else {
    m.result='pass'; m.diff='已整改：'+UI.val('sm_note'); UI.toast('已生成DDL变更并整改完成，复检通过', 'success');
  }
};
A.smRecheck = function(id){
  var m = DB.stdMappings.find(function(x){return x.id===id;});
  UI.toast('正在复检 '+m.table+'.'+m.field+' ...', 'info');
  setTimeout(function(){ m.result='pass'; m.diff='复检通过：类型/长度/格式约束一致'; m.checkedAt=now+' 22:55'; UI.toast('复检通过', 'success'); App.resolve(); }, 800);
};

/* ---- 标准审批 ---- */
App.reg('#/std/approval', '标准审批', function(){
  var html = UI.pageHead('标准审批', '标准变更审批流：起草 → 评审 → 发布；审批通过自动更新标准版本并通知映射方整改复检');
  html += UI.card('审批单列表', UI.tbl({
    id:'t_sa', rowKey:'id', pageSize:8, searchKeys:['id','target','proposer'], searchPh:'搜索单号/对象',
    filters:[{k:'status', label:'状态', options:[{v:'review',t:'评审中'},{v:'published',t:'已发布'},{v:'reject',t:'已驳回'}]}],
    data:function(){ return DB.stdApprovals; },
    cols:[
      {t:'审批单', k:'id', render:function(r){return '<b>'+r.id+'</b><div style="font-size:11px;color:var(--text-3)">'+r.type+'</div>';}},
      {t:'变更对象', k:'target'},
      {t:'发起人', k:'proposer'},
      {t:'提交时间', k:'submitAt'},
      {t:'流程进度', render:function(r){
        return '<div style="display:flex;gap:4px;align-items:center">'+r.flow.map(function(f,i){
          return '<span class="tag '+(i<r.current?'tag-green':i===r.current?'tag-blue':'tag-gray')+'" style="height:18px;font-size:10px">'+f+'</span>'+(i<r.flow.length-1?'<span style="color:var(--text-3);font-size:10px">→</span>':'');}).join('')+'</div>';}},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      if(r.status!=='review') return '<a onclick="A.saDetail(\''+r.id+'\')">详情</a>';
      return '<a onclick="A.saApprove(\''+r.id+'\')">评审通过</a><a class="danger" onclick="A.saReject(\''+r.id+'\')">驳回</a><a onclick="A.saDetail(\''+r.id+'\')">详情</a>';
    }}));
  return html;
});
A.saDetail = function(id){
  var a = DB.stdApprovals.find(function(x){return x.id===id;});
  UI.modal({title:'审批详情 - '+a.id, w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.desc([['类型', a.type],['对象', a.target],['发起人', a.proposer],['提交时间', a.submitAt],['状态', st(a.status)],['意见', a.opinion||'（无）']])
    + UI.timeline(a.flow.map(function(f,i){
      var done = i < a.current;
      return {cls: done?'ok':(i===a.current?'warn':''), title:f, time: done? '已完成':'',
        body: i===1&&!done? '评审要点：类型/长度/格式约束合理性、下游影响面':(i===2&&!done? '发布后自动通知映射方整改复检':'')};}))});
};
A.saApprove = function(id){
  var a = DB.stdApprovals.find(function(x){return x.id===id;});
  UI.confirm({title:'评审通过', msg:'确认通过「'+a.target+'」的评审？', detail:'通过后进入发布环节。', onOk:function(){
    a.current = 2; setTimeout(function(){ a.current=3; a.status='published'; a.opinion='评审通过，已发布执行'; UI.toast('「'+a.target+'」已发布', 'success'); App.resolve(); }, 800);
    a.status = 'approving'; UI.toast('评审通过，正在发布...', 'success'); App.resolve();
  }});
};
A.saReject = function(id){
  var a = DB.stdApprovals.find(function(x){return x.id===id;});
  UI.drawer({title:'驳回 - '+a.target, body: UI.fTextarea('驳回意见（必填）', 'sa_opinion', {rows:3, req:true}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-danger" onclick="A.saRejectSave(\''+id+'\')">确认驳回</button>'});
};
A.saRejectSave = function(id){
  var a = DB.stdApprovals.find(function(x){return x.id===id;});
  if(!UI.val('sa_opinion')){ UI.toast('请填写驳回意见', 'warn'); return; }
  a.status='reject'; a.opinion=UI.val('sa_opinion');
  UI.toast('已驳回并通知发起人', 'info');
};

/* ==================== M10i 指标管理 ==================== */
/* ---- 指标目录 ---- */
App.reg('#/ind/list', '指标目录', function(){
  var html = UI.pageHead('指标管理',
    '统一指标定义：原子/派生/计算指标，业务口径与技术口径双登记，版本化管理，杜绝同名不同义',
    '<button class="btn btn-primary" onclick="A.indCreate()">+ 新建指标</button>'
    +'<button class="btn" onclick="App.go(\'#/ind/consistency\')">一致性检查</button>');
  html += UI.card('指标目录', UI.tbl({
    id:'t_ind', rowKey:'id', pageSize:8, searchKeys:['id','name','en','domain'], searchPh:'搜索指标',
    filters:[
      {k:'type', label:'类型', options:[{v:'原子',t:'原子指标'},{v:'派生',t:'派生指标'},{v:'计算',t:'计算指标'}]},
      {k:'domain', label:'主题域', options:DB.bizDomains.map(function(d){return {v:d.name,t:d.name};})},
      {k:'status', label:'状态', options:[{v:'published',t:'已发布'},{v:'review',t:'评审中'}]}
    ],
    data:function(){ return DB.indicators; },
    cols:[
      {t:'指标', k:'name', sortable:true, render:function(r){
        return '<div><a onclick="A.indDetail(\''+r.id+'\')"><b>'+r.name+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+r.en+' · v'+r.v+'</div></div>';}},
      {t:'类型', k:'type', render:function(r){return tag(r.type, r.type==='原子'?'blue':r.type==='派生'?'purple':'cyan');}},
      {t:'业务口径', k:'bizDef', render:function(r){return '<span style="font-size:11.5px">'+UI.esc(r.bizDef)+'</span>';}},
      {t:'来源表', k:'srcTable', render:function(r){return '<span class="mono" style="font-size:11.5px">'+r.srcTable+'</span>';}},
      {t:'主题域', k:'domain'},
      {t:'状态', k:'status', render:function(r){return st(r.status);}},
      {t:'负责人', k:'owner'}
    ],
    ops:function(r){
      return '<a onclick="A.indDetail(\''+r.id+'\')">详情</a>'
        +'<a onclick="App.go(\'#/ind/board\')">趋势</a>'
        +(r.status==='published'? '<a onclick="A.indChange(\''+r.id+'\')">口径变更</a>' : '<a onclick="App.go(\'#/ind/approval\')">审批进度</a>')
        +'<a class="danger" onclick="A.indDel(\''+r.id+'\')">删除</a>';
    }}));
  return html;
});
A.indDetail = function(id){
  var d = DB.indicators.find(function(x){return x.id===id;});
  UI.drawer({title:'指标详情 - '+d.name, w:'w-xl', body:
    UI.desc([['编号', d.id],['英文名','<span class="mono">'+d.en+'</span>'],['类型', tag(d.type,'blue')],['主题域', d.domain],['版本','v'+d.v],['状态', st(d.status)],['负责人', d.owner],
      ['业务口径', d.bizDef],['技术口径','<span class="mono" style="font-size:11.5px">'+UI.esc(d.techDef)+'</span>'],
      ['来源','<span class="mono">'+d.srcTable+'.'+(d.srcField||'-')+'</span>'],
      ['产出', (d.outTable&&d.outTable!=='-'? '<span class="mono">'+d.outTable+'</span>（'+d.outTask+'）' : '未落表（即席计算）')],
      ['统计周期', d.period],['维度', d.dims]])
    + '<div class="card-head" style="border-bottom:none;padding:10px 0 6px"><h3>版本历史</h3></div>'
    + UI.timeline(d.versions.map(function(v){return {title:'v'+v.v+' · '+UI.esc(v.note), time:v.date+' · '+v.author};})),
    footer:'<button class="btn" onclick="UI.closeDrawer()">关闭</button><button class="btn btn-primary" onclick="UI.closeDrawer();A.indChange(\''+d.id+'\')">发起口径变更</button>'});
};
A.indFormFields = function(d){
  return '<div class="form-grid">'
    + UI.fInput('指标名称', 'ind_name', {value:d.name, req:true})
    + UI.fInput('英文名', 'ind_en', {value:d.en, req:true})
    + UI.fSelect('指标类型', 'ind_type', [{v:'原子',t:'原子指标'},{v:'派生',t:'派生指标'},{v:'计算',t:'计算指标'}], {value:d.type||'原子'})
    + UI.fSelect('主题域', 'ind_domain', DB.bizDomains.map(function(x){return x.name;}), {value:d.domain||'交易域'})
    + UI.fTextarea('业务口径定义', 'ind_biz', {value:d.bizDef, rows:2, req:true, full:true})
    + UI.fTextarea('技术口径（SQL/公式）', 'ind_tech', {value:d.techDef, rows:2, req:true, full:true})
    + UI.fSelect('来源表', 'ind_src', DB.metaTables.map(function(t){return {v:t.name,t:t.name};}), {value:d.srcTable})
    + UI.fInput('来源字段', 'ind_srcf', {value:d.srcField})
    + UI.fSelect('统计周期', 'ind_period', ['日','近7天','本月','实时','-'], {value:d.period||'日'})
    + UI.fInput('维度', 'ind_dims', {value:d.dims, ph:'如：日期/渠道'})
    + '</div>';
};
A.indCreate = function(){
  UI.drawer({title:'新建指标', w:'w-lg', body:A.indFormFields({}), onOk:function(){
    var name = UI.val('ind_name');
    if(!name||!UI.val('ind_biz')){ UI.toast('请填写指标名称与业务口径', 'warn'); return false; }
    var dup = DB.indicators.some(function(i){return i.name===name;});
    if(dup){ UI.toast('已存在同名指标「'+name+'」，禁止同名不同义', 'error'); return false; }
    DB.indicators.push({id:'METRIC_0'+(DB.indicators.length+1), name:name, en:UI.val('ind_en'), type:UI.val('ind_type'), bizDef:UI.val('ind_biz'), techDef:UI.val('ind_tech'), srcTable:UI.val('ind_src'), srcField:UI.val('ind_srcf'), outTable:'-', outTask:'-', period:UI.val('ind_period'), dims:UI.val('ind_dims'), owner:DB.user.name, domain:UI.val('ind_domain'), status:'review', v:1, trend:[0,0,0,0,0,0,0,0], unit:'-', versions:[{v:1,date:now,note:'初版',author:DB.user.name}]});
    UI.toast('指标已创建（评审中），可在指标审批中跟踪', 'success');
  }});
};
A.indChange = function(id){
  var d = DB.indicators.find(function(x){return x.id===id;});
  UI.drawer({title:'口径变更 - '+d.name+'（当前 v'+d.v+'）', w:'w-lg', body:
    UI.fTextarea('变更原因（必填）', 'ic_reason', {rows:3, req:true})
    + UI.fTextarea('新业务口径', 'ic_biz', {value:d.bizDef, rows:2})
    + UI.fTextarea('新技术口径', 'ic_tech', {value:d.techDef, rows:2})
    + '<div class="lock-tip">变更提交后进入评审流（发起 → 评审 → 发布），发布后版本 v'+(d.v+1)+'，并触发一致性复检。</div>',
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-primary" onclick="A.indChangeSave(\''+id+'\')">提交变更评审</button>'});
};
A.indChangeSave = function(id){
  var d = DB.indicators.find(function(x){return x.id===id;});
  if(!UI.val('ic_reason')){ UI.toast('请填写变更原因', 'warn'); return; }
  d.status = 'review';
  DB.indApprovals.unshift({id:'IA'+now.replace(/-/g,'')+'-0'+(DB.indApprovals.length+1), metric:d.id+' '+d.name+'（v'+d.v+'→v'+(d.v+1)+'）', proposer:DB.user.name, reason:UI.val('ic_reason'), submitAt:now+' 23:00', flow:['发起','评审','发布'], current:1, status:'review'});
  UI.toast('变更已提交评审（IA 单已生成）', 'success'); App.go('#/ind/approval');
};
A.indDel = function(id){
  var d = DB.indicators.find(function(x){return x.id===id;});
  var used = DB.indicators.some(function(i){return i.baseMetric===id;}) || DB.impactExample.downIndicators.some(function(x){return x.code===id;});
  if(used){ UI.confirm({title:'无法删除', danger:true, msg:'指标「'+d.name+'」被派生指标或报表引用', detail:'请先解除引用或走口径变更流程。'}); }
  else UI.delRow(DB.indicators, 'id', id, d.name);
};

/* ---- 指标审批 ---- */
App.reg('#/ind/approval', '指标审批', function(){
  var html = UI.pageHead('指标审批', '口径变更审批流：发起 → 评审 → 发布；发布后自动升级版本并触发一致性复检');
  html += UI.card('审批单', UI.tbl({
    id:'t_ia', rowKey:'id', pageSize:8, searchKeys:['id','metric','proposer'], searchPh:'搜索单号/指标',
    filters:[{k:'status', label:'状态', options:[{v:'review',t:'评审中'},{v:'published',t:'已发布'},{v:'reject',t:'已驳回'}]}],
    data:function(){ return DB.indApprovals; },
    cols:[
      {t:'审批单', k:'id', render:function(r){return '<b>'+r.id+'</b>';}},
      {t:'指标变更', k:'metric'},
      {t:'变更原因', k:'reason', render:function(r){return '<span style="font-size:11.5px">'+UI.esc(r.reason)+'</span>';}},
      {t:'发起人', k:'proposer'},{t:'提交时间', k:'submitAt'},
      {t:'状态', k:'status', render:function(r){return st(r.status);}}
    ],
    ops:function(r){
      if(r.status!=='review') return '<a onclick="A.iaDetail(\''+r.id+'\')">详情</a>';
      return '<a onclick="A.iaApprove(\''+r.id+'\')">通过</a><a class="danger" onclick="A.iaReject(\''+r.id+'\')">驳回</a><a onclick="A.iaDetail(\''+r.id+'\')">详情</a>';
    }}));
  return html;
});
A.iaDetail = function(id){
  var a = DB.indApprovals.find(function(x){return x.id===id;});
  UI.modal({title:'审批详情 - '+a.id, w:'w-md', footer:'<button class="btn" onclick="UI.closeModal()">关闭</button>', body:
    UI.desc([['指标变更', a.metric],['原因', a.reason],['发起人', a.proposer],['提交时间', a.submitAt],['状态', st(a.status)],['意见', a.opinion||'（无）']])
    + UI.timeline(a.flow.map(function(f,i){return {cls:i<a.current?'ok':(i===a.current?'warn':''), title:f, time:i<a.current?'已完成':''};}))});
};
A.iaApprove = function(id){
  var a = DB.indApprovals.find(function(x){return x.id===id;});
  UI.confirm({title:'评审通过', msg:'确认通过「'+a.metric+'」？', detail:'通过后指标版本升级并触发一致性复检。', onOk:function(){
    var mid = a.metric.split(' ')[0];
    var m = DB.indicators.find(function(x){return x.id===mid;});
    if(m){ m.v += 1; m.status = 'published'; m.versions.unshift({v:m.v, date:now, note:a.reason, author:a.proposer}); }
    a.current=3; a.status='published'; a.opinion='评审通过，版本已升级';
    UI.toast('「'+a.metric+'」已发布，版本升级', 'success'); App.resolve();
  }});
};
A.iaReject = function(id){
  var a = DB.indApprovals.find(function(x){return x.id===id;});
  UI.drawer({title:'驳回 - '+a.metric, body: UI.fTextarea('驳回意见（必填）', 'ia_opinion', {rows:3, req:true}),
    footer:'<button class="btn" onclick="UI.closeDrawer()">取消</button><button class="btn btn-danger" onclick="A.iaRejectSave(\''+id+'\')">确认驳回</button>'});
};
A.iaRejectSave = function(id){
  var a = DB.indApprovals.find(function(x){return x.id===id;});
  if(!UI.val('ia_opinion')){ UI.toast('请填写驳回意见', 'warn'); return; }
  a.status='reject'; a.opinion=UI.val('ia_opinion');
  UI.toast('已驳回并通知发起人', 'info');
};

/* ---- 指标看板 ---- */
App.reg('#/ind/board', '指标看板', function(){
  var html = UI.pageHead('指标看板', '核心指标运行趋势与维度拆解（数据源：ads_kpi_report / dws_pay_summary_daily）');
  var ind = DB.indicators[0];
  html += '<div class="grid" style="grid-template-columns:1.5fr 1fr;gap:16px;align-items:flex-start">'
    + UI.card('核心指标趋势（'+ind.name+' · 单位 '+ind.unit+'）',
      '<div class="grid grid-4" style="margin-bottom:12px">'
      +'<div class="stat-card" style="padding:11px"><div><div class="stat-num" style="font-size:19px">'+ind.trend[7]+'</div><div class="stat-label">今日 '+ind.unit+'</div></div></div>'
      +'<div class="stat-card" style="padding:11px"><div><div class="stat-num" style="font-size:19px;color:var(--success)">+4.2%</div><div class="stat-label">日环比</div></div></div>'
      +'<div class="stat-card" style="padding:11px"><div><div class="stat-num" style="font-size:19px">'+Math.round(ind.trend.reduce(function(a,b){return a+b;},0)/ind.trend.length)+'</div><div class="stat-label">近8日均</div></div></div>'
      +'<div class="stat-card" style="padding:11px"><div><div class="stat-num" style="font-size:19px;color:var(--success)">+'+((ind.trend[7]/ind.trend[0]*100)-100).toFixed(1)+'%</div><div class="stat-label">较8日前</div></div></div></div>'
      + Charts.line({labels:DB.qcScoreTrend.labels, series:[{name:ind.name, color:'#1668dc', data:ind.trend}]})
      + '<div style="display:flex;gap:8px;margin-top:10px"><button class="btn" onclick="A.ibSwitch(0)">支付金额</button><button class="btn" onclick="A.ibSwitch(2)">支付用户数</button><button class="btn" onclick="A.ibSwitch(1)">近7天支付金额</button></div>')
    + UI.card('渠道拆解（支付金额占比）', Charts.donut({items:[
        {name:'支付宝', value:528210, color:'#1668dc'},{name:'微信支付', value:451870, color:'#16a34a'},
        {name:'银联', value:122400, color:'#d97706'},{name:'银行卡', value:68900, color:'#7c3aed'}], center:'117万', centerLabel:'昨日支付金额'})
      + '<div class="lock-tip" style="margin-top:8px">数据来源 dws_pay_summary_daily dt=2026-09-11，与指标「支付金额」技术口径一致（不含退款）。</div>')
    + '</div>';
  html += UI.card('指标健康度', '<div class="grid grid-3">'
    + DB.indicators.slice(0,3).map(function(m){
      return '<div class="stat-card"><span class="type-icon" style="background:#16a34a">✦</span><div><b style="font-size:12.5px">'+m.name+'</b><div style="font-size:11px;color:var(--text-3)">产出正常 · 口径一致 · 负责人 '+m.owner+'</div></div></div>';
    }).join('')+'</div>', '<button class="btn" onclick="App.go(\'#/ind/consistency\')">一致性检查</button>');
  return html;
});
A.ibSwitch = function(idx){
  var m = DB.indicators[idx];
  UI.toast('已切换至指标「'+m.name+'」（'+m.bizDef+'）', 'info'); App.resolve();
};

/* ---- 一致性检查 ---- */
App.reg('#/ind/consistency', '一致性检查', function(){
  var html = UI.pageHead('指标一致性检查',
    '同一指标在报表/看板/宽表中的口径一致性扫描，发现同名不同义即生成整改任务');
  html += '<div class="grid grid-3" style="margin-bottom:16px">'
    +'<div class="stat-card"><span class="type-icon" style="background:#1668dc">⇋</span><div><div class="stat-num">'+DB.indConsistency.length+'</div><div class="stat-label">检查指标数</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#16a34a">✓</span><div><div class="stat-num">'+DB.indConsistency.filter(function(c){return c.result==='pass';}).length+'</div><div class="stat-label">口径一致</div></div></div>'
    +'<div class="stat-card"><span class="type-icon" style="background:#e5484d">✗</span><div><div class="stat-num">'+DB.indConsistency.filter(function(c){return c.result==='fail';}).length+'</div><div class="stat-label">口径冲突</div></div></div></div>';
  html += UI.card('检查结果', UI.tbl({
    id:'t_ic', rowKey:'metric', pageSize:8, searchKeys:['metric'], data:function(){ return DB.indConsistency; },
    cols:[
      {t:'指标', k:'metric', render:function(r){return '<b>'+r.metric+'</b>';}},
      {t:'使用位置', render:function(r){return r.places.map(function(p){return '<span class="tag tag-outline" style="margin:1px 3px 1px 0">'+p+'</span>';}).join('');}},
      {t:'结果', k:'result', render:function(r){return st(r.result==='pass'?'pass':'reject');}},
      {t:'差异详情', k:'detail'}
    ],
    ops:function(r){ return r.result==='fail'? '<a onclick="A.icFix(\''+r.metric+'\')">发起整改</a>' : '<a onclick="UI.toast(\''+r.metric+'：'+UI.esc(r.detail)+'\',\'info\')">详情</a>'; }}));
  return html;
});
A.icFix = function(metric){
  UI.confirm({title:'发起口径整改', msg:'对「'+metric+'」发起口径对齐整改？', detail:'整改方向：按标准口径（不含退款）修正经营日报计算逻辑，修正后复检。', onOk:function(){
    var c = DB.indConsistency.find(function(x){return x.metric===metric;});
    c.result='pass'; c.detail='已整改：经营日报调整为标准口径（不含退款），复检一致';
    UI.toast('整改完成，复检通过', 'success'); App.resolve();
  }});
};
})();
