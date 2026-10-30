/* ============================================================
   M06 流数据处理（P0：实时采集CDC/SQL流计算/窗口/水位线/状态/Checkpoint/预览）
   + 可视化流设计器（#/stream/design/:id，对标 M05 ETL 设计器）
   ============================================================ */
(function(){
App.reg('#/stream/list', '流处理作业', function(){
  var html = UI.pageHead('流数据处理',
    'Kafka 消息队列接入（P0 暂定支撑 Kafka）+ Flink SQL 流计算；实时风控/用户行为/实时推荐等业务场景排后期',
    '<button class="btn btn-primary" onclick="A.stCreate()">+ 新建流作业</button>'
    +'<button class="btn" onclick="UI.toast(\'集群资源：Flink TaskManager 2/2 正常，Slot 使用 14/16\',\'info\')">资源概览</button>');
  html += UI.card('流作业列表', UI.tbl({
    id:'t_st', rowKey:'id', pageSize:8, searchKeys:['name','type','source','sink','owner'], searchPh:'搜索作业/Topic/Sink',
    filters:[{k:'status', label:'状态', options:[{v:'running',t:'运行中'},{v:'paused',t:'已暂停'},{v:'stopped',t:'已停止'}]}],
    data:function(){ return DB.streamJobs; },
    cols:[
      {t:'作业', k:'name', render:function(r){ return '<a onclick="App.go(\'#/stream/detail/'+r.id+'\')"><b>'+UI.esc(r.name)+'</b></a><div style="font-size:11px;color:var(--text-3)">'+r.id+' · '+r.type+' · 负责人 '+r.owner+'</div>'; }},
      {t:'数据链路', render:function(r){ return '<div class="mono" style="font-size:11px">'+UI.esc(r.source)+'</div><div class="mono" style="font-size:11px;color:var(--primary)">→ '+UI.esc(r.sink)+'</div>'; }},
      {t:'吞吐/延迟', render:function(r){ return '<span class="mono">'+fmt(r.metrics.tps)+' 条/s</span><div style="font-size:11px;color:var(--text-3)">端到端 '+r.metrics.latency+'</div>'; }},
      {t:'Checkpoint', render:function(r){ return r.checkpoint.interval==='-'?'-':'<span style="font-size:12px">'+r.checkpoint.interval+' · '+r.checkpoint.mode+'</span><div style="font-size:11px;color:var(--text-3)">成功率 '+r.checkpoint.successRate+'</div>'; }},
      {t:'状态', k:'status', render:function(r){ return st(r.status); }}
    ],
    ops:function(r){
      var o = '';
      if(r.status==='running') o = '<a onclick="A.stPause(\''+r.id+'\')">暂停</a><a onclick="A.stStop(\''+r.id+'\')">停止</a>';
      else if(r.status==='paused') o = '<a onclick="A.stResume(\''+r.id+'\')">恢复</a><a onclick="A.stStop(\''+r.id+'\')">停止</a>';
      else o = '<a onclick="A.stStart(\''+r.id+'\')">启动</a>';
      return '<a onclick="App.go(\'#/stream/design/'+r.id+'\')">设计器</a><a onclick="App.go(\'#/stream/detail/'+r.id+'\')">详情</a>'+o;
    }
  }));
  html += '<div class="grid grid-2">'
    + UI.card('窗口计算（Flink SQL）', UI.tbl({id:'t_win', rowKey:'name', pageSize:5, searchKeys:['name'],
      data:function(){ return DB.windows; }, cols:[{t:'窗口类型',k:'name'},{t:'说明',k:'desc'},{t:'示例',k:'eg'}], ops:null}))
    + UI.card('时间语义与水位线', UI.tbl({id:'t_ts', rowKey:'name', pageSize:5, searchKeys:['name'],
      data:function(){ return DB.timeSemantics; }, cols:[{t:'时间语义',k:'name'},{t:'说明',k:'desc'},{t:'适用',k:'use'}], ops:null}));
  html += UI.card('核心能力说明', '<div class="grid grid-4">'
    +'<div class="stat-card"><div><b>实时数据采集</b><div class="f-help">CDC捕获Binlog/WAL变更、日志实时采集、IoT接入</div></div></div>'
    +'<div class="stat-card"><div><b>状态管理</b><div class="f-help">Keyed/Operator State，RocksDB状态后端支撑大状态</div></div></div>'
    +'<div class="stat-card"><div><b>Checkpoint容错</b><div class="f-help">周期Checkpoint，Exactly-Once精确一次，故障自动恢复</div></div></div>'
    +'<div class="stat-card"><div><b>实时预览</b><div class="f-help">调试时实时查看中间结果，降低SQL开发门槛</div></div></div></div>'
    +'<div class="banner banner-warn"><span class="b-ico">⚠</span><span>CEP 复杂事件处理、实时风控/用户行为/实时推荐等业务场景已明确移出 P0（后期迭代）。</span></div>');
  return html;
});

/* 新建作业 */
A.stCreate = function(){
  UI.drawer({title:'新建流处理作业', w:'w-lg', body:
    UI.fInput('作业名称', 'sj_name', {req:true, ph:'如：订单支付实时入仓'})
    + UI.fSelect('作业类型', 'sj_type', [{v:'Flink SQL',t:'Flink SQL 流计算（推荐）'},{v:'CDC采集',t:'CDC 实时采集（Binlog/WAL → Kafka）'}], {value:'Flink SQL'})
    + UI.fSelect('数据源', 'sj_src', [{v:'Kafka: topic_order_pay',t:'Kafka: topic_order_pay'},{v:'Kafka: topic_iot_heartbeat',t:'Kafka: topic_iot_heartbeat'},{v:'MySQL Binlog: biz_test.inventory',t:'MySQL Binlog（CDC）'}])
    + UI.fSelect('写入目标', 'sj_sink', [{v:'Doris: dwd_order_pay_rt',t:'Doris 实时数仓'},{v:'Kafka: topic_inventory_cdc',t:'Kafka 下游Topic'},{v:'打印控制台',t:'打印控制台（调试）'}])
    + UI.fSelect('并行度', 'sj_para', [1,2,4,8].map(function(n){return {v:n,t:n};}), {value:4})
    + UI.fSelect('Checkpoint间隔', 'sj_ck', [{v:'30s',t:'30秒'},{v:'60s',t:'60秒（推荐）'},{v:'120s',t:'120秒'}], {value:'60s'})
    + UI.fTextarea('Flink SQL', 'sj_sql', {rows:7, mono:true, value:"INSERT INTO dwd_order_pay_rt\nSELECT pay_id, order_id, user_id, pay_amount, pay_status,\n       TO_DATE(pay_time) AS dt\nFROM kafka_order_pay\nWHERE pay_amount IS NOT NULL;", help:'支持窗口函数（TUMBLE/HOP/SESSION）、事件时间与Watermark'}),
    onOk:function(){
      var id = 'SJ'+String(DB.streamJobs.length+1).padStart(3,'0');
      DB.streamJobs.push({id:id, name:UI.val('sj_name'), type:UI.val('sj_type'), source:UI.val('sj_src'), sink:UI.val('sj_sink'), status:'stopped',
        checkpoint:{interval:UI.val('sj_ck'), mode:'Exactly-Once', backend:'RocksDB', lastOk:'-', successRate:'-'},
        metrics:{tps:0, latency:'-', inTotal:0, outTotal:0, watermark:'-'}, sql:UI.val('sj_sql'), owner:DB.user.name, parallelism:+UI.val('sj_para'), uptime:'-', createdAt:'2026-09-12 22:45'});
      UI.toast('流作业已创建（'+id+'），点击「启动」运行', 'success');
    }});
};
A.stPause = function(id){ var j = DB.streamJobs.find(function(x){return x.id===id;}); j.status='paused'; UI.toast('作业已暂停（State保留，可恢复）', 'info'); App.resolve(); };
A.stResume = function(id){ var j = DB.streamJobs.find(function(x){return x.id===id;}); j.status='running'; UI.toast('作业已从最近Checkpoint恢复运行', 'success'); App.resolve(); };
A.stStop = function(id){
  UI.confirm({title:'停止作业', danger:true, msg:'确认停止作业「'+DB.streamJobs.find(function(x){return x.id===id;}).name+'」？', detail:'停止后将释放Slot资源；可选保留Savepoint用于恢复。', onOk:function(){
    var j = DB.streamJobs.find(function(x){return x.id===id;}); j.status='stopped'; UI.toast('作业已停止', 'success'); App.resolve();
  }});
};
A.stStart = function(id){ var j = DB.streamJobs.find(function(x){return x.id===id;}); j.status='running'; UI.toast('作业启动中：提交Flink集群 → 初始化State → 运行', 'info'); setTimeout(function(){ UI.toast('作业已运行', 'success'); App.resolve(); }, 1000); };

/* 作业详情 */
App.reg('#/stream/detail/:id', '流作业详情', function(p){
  var j = DB.streamJobs.find(function(x){return x.id===p.id;});
  if(!j) return '<div class="empty">作业不存在</div>';
  var html = UI.pageHead('<a onclick="App.go(\'#/stream/list\')">← 流处理作业</a> / '+j.name,
    j.id+' · '+j.type+' · '+UI.esc(j.source)+' → '+UI.esc(j.sink)+' · 并行度 '+j.parallelism+' · 运行时长 '+j.uptime,
    (j.status==='running'?'<button class="btn" onclick="A.stPause(\''+j.id+'\')">暂停</button>':'<button class="btn btn-primary" onclick="A.stStart(\''+j.id+'\')">▶ 启动</button>')
    + st(j.status));
  var tabs = UI.tabs('stTab', [{label:'SQL开发',render:1},{label:'运行拓扑与指标',render:1},{label:'Checkpoint与状态',render:1},{label:'实时数据预览',render:1}], 0);
  html += '<div class="card no-head"><div class="card-body">'+tabs+'<div id="stTabBody"></div></div></div>';
  UI._tabCb['stTab'] = function(i){ A._stTab(i, j); };
  App.onAfterRender(function(mm){ if(mm.path.indexOf('#/stream/detail/')===0) A._stTab(0, j); });
  return html;
});
A._stTab = function(i, j){
  var b = document.getElementById('stTabBody');
  if(i===0){
    b.innerHTML = '<div class="editor-wrap"><div class="editor-toolbar"><b style="font-size:12.5px">Flink SQL</b><span style="flex:1"></span>'
      +'<button class="btn btn-sm" onclick="UI.toast(\'SQL格式化完成\',\'success\')">格式化</button>'
      +'<button class="btn btn-sm" onclick="UI.toast(\'语法校验通过，产出表 dwd_order_pay_rt 已解析\',\'success\')">校验</button>'
      +'<button class="btn btn-primary btn-sm" onclick="UI.toast(\'已保存并应用（作业将重启生效）\',\'success\')">保存并生效</button></div>'
      +'<textarea class="editor-area" style="min-height:240px">'+UI.esc(j.sql)+'</textarea></div>'
      +'<div class="grid grid-2" style="margin-top:14px">'
      + UI.card('窗口参考', DB.windows.map(function(w){ return '<div class="kv-row"><span class="k">'+w.name+'</span><span class="v">'+w.desc+'；例：'+w.eg+'</span></div>'; }).join(''))
      + UI.card('时间语义', DB.timeSemantics.map(function(w){ return '<div class="kv-row"><span class="k">'+w.name+'</span><span class="v">'+w.desc+'；适用：'+w.use+'</span></div>'; }).join(''))
      + '</div>';
  }
  if(i===1){
    b.innerHTML = UI.card('运行指标', '<div class="grid grid-4">'
      +'<div class="stat-card"><div><div class="stat-num">'+fmt(j.metrics.tps)+'</div><div class="stat-label">当前吞吐（条/s）</div></div></div>'
      +'<div class="stat-card"><div><div class="stat-num" style="font-size:17px">'+j.metrics.latency+'</div><div class="stat-label">端到端延迟</div></div></div>'
      +'<div class="stat-card"><div><div class="stat-num" style="font-size:17px">'+fmt(j.metrics.inTotal)+'</div><div class="stat-label">累计输入</div></div></div>'
      +'<div class="stat-card"><div><div class="stat-num" style="font-size:17px">'+fmt(j.metrics.outTotal)+'</div><div class="stat-label">累计输出</div></div></div></div>'
      +'<div class="kv-row" style="margin-top:8px"><span class="k">Watermark</span><span class="v mono">'+j.metrics.watermark+'</span></div>'
      +'<div class="kv-row"><span class="k">时间语义</span><span class="v">事件时间（Event Time）+ Watermark 乱序容忍 4s</span></div>')
      + UI.card('执行拓扑（Source → 算子 → Sink）',
        '<div class="dag-wrap" style="min-height:180px"><svg class="dag-svg" width="820" height="170">'
        +'<g class="dag-node"><rect class="n-box" x="30" y="50" width="130" height="60" rx="8"/><text x="95" y="76" text-anchor="middle" font-size="11" fill="#5b6478">Source</text><text x="95" y="95" text-anchor="middle" font-size="12" font-weight="600">Kafka Topic</text></g>'
        +'<line class="dag-edge ok-edge" x1="160" y1="80" x2="215" y2="80"/>'
        +'<g class="dag-node"><rect class="n-box" x="215" y="50" width="150" height="60" rx="8"/><text x="290" y="76" text-anchor="middle" font-size="11" fill="#5b6478">FlatMap/Filter</text><text x="290" y="95" text-anchor="middle" font-size="12" font-weight="600">并行度 '+j.parallelism+'</text></g>'
        +'<line class="dag-edge ok-edge" x1="365" y1="80" x2="420" y2="80"/>'
        +'<g class="dag-node"><rect class="n-box" x="420" y="50" width="150" height="60" rx="8"/><text x="495" y="76" text-anchor="middle" font-size="11" fill="#5b6478">Keyed Process</text><text x="495" y="95" text-anchor="middle" font-size="12" font-weight="600">RocksDB State</text></g>'
        +'<line class="dag-edge ok-edge" x1="570" y1="80" x2="625" y2="80"/>'
        +'<g class="dag-node"><rect class="n-box" x="625" y="50" width="130" height="60" rx="8"/><text x="690" y="76" text-anchor="middle" font-size="11" fill="#5b6478">Sink</text><text x="690" y="95" text-anchor="middle" font-size="12" font-weight="600">Doris Stream Load</text></g>'
        +'</svg></div>');
  }
  if(i===2){
    b.innerHTML = UI.card('Checkpoint 配置', '<div class="form-grid">'
      + UI.fSelect('间隔', 'ck_int', [{v:'30s',t:'30秒'},{v:'60s',t:'60秒'},{v:'120s',t:'120秒'}], {value:j.checkpoint.interval})
      + UI.fSelect('语义', 'ck_mode', [{v:'Exactly-Once',t:'Exactly-Once（精确一次，推荐）'},{v:'At-Least-Once',t:'At-Least-Once'}], {value:j.checkpoint.mode})
      + UI.fSelect('状态后端', 'ck_be', [{v:'RocksDB',t:'RocksDB（大状态，推荐）'},{v:'HashMap',t:'HashMap（小状态）'}], {value:j.checkpoint.backend})
      + '</div><button class="btn btn-primary" onclick="A.stCkSave(\''+j.id+'\')">保存配置</button>')
      + UI.card('Checkpoint 运行记录',
        UI.tbl({id:'t_ck', rowKey:'id', pageSize:5, searchKeys:['id'],
          data:function(){ return [{id:'ck-12846', t:'22:28:40', d:'2.1s', s:'完成', size:'186MB'},{id:'ck-12845', t:'22:27:40', d:'6.0s', s:'完成', size:'186MB'},{id:'ck-12844', t:'22:26:40', d:'1.8s', s:'完成', size:'185MB'}]; },
          cols:[{t:'Checkpoint',k:'id',render:function(r){return '<span class="mono">'+r.id+'</span>';}},{t:'完成时间',k:'t'},{t:'耗时',k:'d'},{t:'状态',k:'s',render:function(r){return st('success');}},{t:'State大小',k:'size'}], ops:null})
        +'<div style="margin-top:10px;font-size:12px;color:var(--text-2)">成功率 '+j.checkpoint.successRate+' · 最近成功 '+j.checkpoint.lastOk+' · 故障自动恢复：从最近完成Checkpoint恢复State</div>');
  }
  if(i===3){
    b.innerHTML = UI.card('实时数据预览（调试）',
      '<div style="display:flex;gap:8px;margin-bottom:10px"><button class="btn btn-primary btn-sm" onclick="A.stPreviewRun()">▶ 开始采样</button><button class="btn btn-sm" onclick="UI.toast(\'采样已停止\',\'info\')">停止采样</button><span style="font-size:12px;color:var(--text-3);align-self:center">采样最新 20 条进入流的数据</span></div>'
      +'<div id="stPvBox">'+UI.tbl({id:'t_stpv', rowKey:'pay_id', pageSize:6, searchKeys:['pay_id'],
        data:function(){ return [
          {pay_id:20260911220301, amount:299.00, ch:'ALIPAY', st:1},
          {pay_id:20260911220302, amount:1299.00, ch:'WECHAT', st:1},
          {pay_id:20260911220303, amount:88.50, ch:'UNIONPAY', st:1},
          {pay_id:20260911220304, amount:-10.00, ch:'WECHAT', st:1},
          {pay_id:20260911220305, amount:4299.00, ch:'BANK', st:0}]; },
        cols:[{t:'pay_id',k:'pay_id',render:function(r){return '<span class="mono">'+r.pay_id+'</span>';}},{t:'pay_amount',k:'amount',render:function(r){return '<span class="mono" style="color:'+(r.amount<0?'var(--danger)':'inherit')+'">'+r.amount.toFixed(2)+'</span>';}},{t:'pay_channel',k:'ch'},{t:'pay_status',k:'st',render:function(r){return r.st?st('success'):st('failed');}}],
        ops:function(r){ return r.amount<0?'<a class="danger" onclick="UI.toast(\'异常样例：负值数据，建议在SQL中过滤 pay_amount>0\',\'warn\')">标记异常</a>':''; }})+'</div>');
  }
};
A.stCkSave = function(id){ var j = DB.streamJobs.find(function(x){return x.id===id;}); Object.assign(j.checkpoint, {interval:UI.val('ck_int'), mode:UI.val('ck_mode'), backend:UI.val('ck_be')}); UI.toast('Checkpoint配置已保存，重启作业后生效', 'success'); };
A.stPreviewRun = function(){ UI.toast('实时采样中：已捕获 5 条（含 1 条异常：pay_amount=-10.00）', 'warn'); };

/* ============================================================
   可视化流设计器（DolphinScheduler 式三栏全屏，对标 M05 ETL 设计器）
   左：流元件库（流源/流转换/流输出/容错运维）拖拽入画布
   中：VC 画布（开始→流源→算子→Sink→结束，hover 摘要、连线、自动排版）
   右：验证与测试面板（链路校验/试运行回放/输入抽样）
   ============================================================ */
A.ST_PALETTE = [
  {cat:'流源（接入）', items:[
    {type:'kafka_source', name:'Kafka Source', icon:'⇊', color:'#0ea5e9', desc:'topic/group/格式', summary:'订阅 Kafka Topic 作为流式输入'},
    {type:'cdc_binlog', name:'CDC-Binlog', icon:'⟳', color:'#0891b2', desc:'库表/位点', summary:'捕获 MySQL Binlog 变更（INSERT/UPDATE/DELETE）'},
    {type:'log_collect', name:'日志采集', icon:'≡', color:'#64748b', desc:'文件日志 tail', summary:'实时采集服务日志文件（tail -F 按行解析）'},
    {type:'iot_access', name:'IoT 接入', icon:'⌁', color:'#7c3aed', desc:'MQTT/网关', summary:'接入 IoT 设备上行数据（MQTT/TCP 网关）'}]},
  {cat:'流转换', items:[
    {type:'keyby', name:'KeyBy 分流', icon:'⑃', color:'#8b5cf6', desc:'按键哈希分区', summary:'按键哈希分流，相同 Key 进入同一子任务'},
    {type:'window', name:'窗口', icon:'⏱', color:'#f59e0b', desc:'滚动/滑动/会话', summary:'窗口聚合：大小/步长/水位线（TUMBLE/HOP/SESSION）'},
    {type:'time_join', name:'时间 Join', icon:'⨝', color:'#d97706', desc:'双流区间关联', summary:'Interval Join：双流按时间边界关联'},
    {type:'state_op', name:'状态算子', icon:'⛁', color:'#2563eb', desc:'RocksDB 状态', summary:'Keyed State + RocksDB 后端，支撑大状态'},
    {type:'cep', name:'CEP 复杂事件', icon:'⧗', color:'#94a3b8', desc:'一期暂缓（移出 P0）', summary:'CEP 一期不做，后期迭代；此处仅占位'}]},
  {cat:'流输出', items:[
    {type:'kafka_sink', name:'Kafka Sink', icon:'⇈', color:'#7c3aed', desc:'写下游 Topic', summary:'结果写回 Kafka 下游 Topic（事务）'},
    {type:'db_sink', name:'数据库 Sink', icon:'⛃', color:'#16a34a', desc:'幂等 upsert', summary:'写入 Doris/GreatDB 目标表（按主键幂等 upsert）'},
    {type:'alert_sink', name:'告警 Sink', icon:'⚠', color:'#e5484d', desc:'规则告警', summary:'命中阈值规则时推送告警（钉钉/短信）'}]},
  {cat:'容错运维', items:[
    {type:'checkpoint', name:'Checkpoint', icon:'⭘', color:'#0ea5e9', desc:'周期/EXACTLY_ONCE', summary:'周期 Checkpoint，EXACTLY_ONCE 精确一次语义'},
    {type:'savepoint', name:'Savepoint', icon:'◉', color:'#1668dc', desc:'手动快照', summary:'触发 Savepoint，用于升级/迁移后状态恢复'},
    {type:'restart', name:'重启策略', icon:'↻', color:'#94a3b8', desc:'固定延迟/失败率', summary:'故障自动重启：固定延迟/失败率策略，超次转 FAILED'}]}
];
/* type -> 元件元信息（一次性建立查找表，避免每次遍历嵌套分组） */
A._stMeta = {};
A.ST_PALETTE.forEach(function(c){ c.items.forEach(function(it){ A._stMeta[it.type] = it; }); });

/* 各类型节点的算子参数表单 + 帮助文案 */
A.ST_FORMS = {
  kafka_source: {fs:[{k:'topic',l:'Topic 名称',ph:'topic_order_pay'},{k:'group',l:'消费组 Group ID',ph:'g_sj001'},{k:'format',l:'反序列化格式',sel:['JSON','Canal-JSON','Avro','CSV']}], help:'订阅 Kafka Topic；消费位点由 Group 自动管理，启动模式 latest-offset。'},
  cdc_binlog: {fs:[{k:'table',l:'库.表',ph:'biz_test.inventory'},{k:'slot',l:'起始位点',ph:'binlog 文件+pos 或 earliest'},{k:'events',l:'捕获事件',sel:['全部（INSERT/UPDATE/DELETE）','仅 INSERT','INSERT+UPDATE']}], help:'基于 Binlog 的 CDC 捕获，对主库无侵入；位点保存在状态后端，重启自动续读。'},
  log_collect: {fs:[{k:'path',l:'日志路径',ph:'/logs/app/*.log'},{k:'pattern',l:'解析规则',sel:['JSON 行','正则提取','原样透传']}], help:'tail -F 采集服务日志，按行解析后进入流；注意日志轮转与乱序。'},
  iot_access: {fs:[{k:'proto',l:'接入协议',sel:['MQTT','TCP','HTTP 网关']},{k:'topic',l:'设备主题',ph:'iot/device/+/heartbeat'}], help:'IoT 网关接入设备上行数据（QoS 1），设备主题支持 +/# 通配。'},
  keyby: {fs:[{k:'key',l:'分流键 Key',ph:'user_id / device_id'},{k:'para',l:'并行度',sel:['1','2','4','8']}], help:'按 Key 哈希分区，相同 Key 路由到同一子任务；Key 选择影响数据倾斜与状态规模。'},
  window: {fs:[{k:'wtype',l:'窗口类型',sel:['滚动 TUMBLE','滑动 HOP','会话 SESSION']},{k:'size',l:'窗口大小',ph:'60s / 5m'},{k:'step',l:'步长（滑动窗口）',ph:'60s；滚动窗口=大小'},{k:'wm',l:'水位线（乱序容忍）',ph:'4s'}], help:'滚动不重叠/滑动重叠/会话按活动间隔切分；事件时间语义需设置 Watermark 容忍乱序。'},
  time_join: {fs:[{k:'jtype',l:'关联类型',sel:['Interval Join','Temporal Join']},{k:'left',l:'左流',ph:'pay_stream'},{k:'right',l:'右流',ph:'order_stream'},{k:'bounds',l:'时间边界',ph:'-5m ~ +5m'}], help:'双流按时间区间关联（Interval Join），超出边界的数据不再匹配；注意双流水位线对齐。'},
  state_op: {fs:[{k:'backend',l:'状态后端',sel:['RocksDB','HashMap']},{k:'ttl',l:'State TTL',ph:'如 24h'},{k:'op',l:'算子逻辑',ph:'如 去重/TopN/最新值'}], help:'大状态使用 RocksDB 后端（磁盘+缓存）；务必配置 State TTL 防止状态无限膨胀。'},
  cep: {fs:[], help:'CEP 复杂事件处理一期暂缓（已移出 P0），此节点仅占位，不参与试运行。'},
  kafka_sink: {fs:[{k:'topic',l:'目标 Topic',ph:'topic_inventory_cdc'},{k:'format',l:'序列化格式',sel:['JSON','Avro']}], help:'结果写回下游 Topic；EXACTLY_ONCE 依赖 Kafka 事务（两阶段提交）。'},
  db_sink: {fs:[{k:'table',l:'目标表',ph:'dwd_order_pay_rt'},{k:'mode',l:'写入模式',sel:['幂等 upsert','append 追加']},{k:'pk',l:'主键（upsert）',ph:'如 pay_id'}], help:'Doris Stream Load / GreatDB upsert；按主键幂等写入，重复数据自动覆盖，不产生重复行。'},
  alert_sink: {fs:[{k:'level',l:'告警级别',sel:['P0-紧急','P1-重要','P2-一般']},{k:'channel',l:'通知渠道',sel:['钉钉','短信','电话']},{k:'rule',l:'告警规则',ph:'如 amount<0 或 5m 内命中>3 次'}], help:'命中规则触发告警推送；注意告警去重与静默窗口，避免告警风暴。'},
  checkpoint: {fs:[{k:'interval',l:'Checkpoint 周期',sel:['30s','60s','120s']},{k:'mode',l:'语义',sel:['EXACTLY_ONCE','AT_LEAST_ONCE']}], help:'周期快照分布式状态；故障时从最近完成 Checkpoint 恢复，端到端 EXACTLY_ONCE。'},
  savepoint: {fs:[{k:'path',l:'存储路径',ph:'hdfs:///sp/'},{k:'trigger',l:'触发方式',sel:['手动','升级前自动']}], help:'Savepoint 为手动触发的快照，用于版本升级/扩缩容后从指定快照恢复状态。'},
  restart: {fs:[{k:'strategy',l:'重启策略',sel:['固定延迟','失败率','无重启']},{k:'delay',l:'重启间隔',ph:'10s'},{k:'attempts',l:'最大尝试次数',ph:'如 3'}], help:'作业失败按策略自动重启；超过最大次数转 FAILED 并触发告警。'}
};
/* summary 展示的参数键 */
A.ST_SUMKEYS = {kafka_source:['topic','group'], cdc_binlog:['table','slot'], log_collect:['path'], iot_access:['proto','topic'],
  keyby:['key'], window:['wtype','size','wm'], time_join:['jtype','bounds'], state_op:['backend','ttl'],
  kafka_sink:['topic'], db_sink:['table','mode'], alert_sink:['level','rule'],
  checkpoint:['interval','mode'], savepoint:['path'], restart:['strategy']};

/* 路由：流设计器 */
App.reg('#/stream/design/:id', '流设计器', function(p){
  var t = DB.streamJobs.find(function(x){return x.id===p.id;});
  if(!t) return '<div class="empty">作业不存在</div>';
  A._stCur = t;
  var head = '<div class="etl-topbar">'
    + '<div><a onclick="App.go(\'#/stream/list\')">← 流作业</a> <b style="margin-left:8px;font-size:14.5px">'+UI.esc(t.name)+'</b>'
    + '<span class="tag" style="margin-left:8px">'+t.type+'</span><span class="mono" style="color:var(--text-3);font-size:12px;margin-left:8px">'+t.id+'</span>'
    + '<span style="font-size:11px;color:var(--text-3);margin-left:10px">'+UI.esc(t.source)+' → '+UI.esc(t.sink)+'</span></div>'
    + '<div style="display:flex;gap:8px">'
    + '<button class="btn btn-sm" onclick="UI.toast(\'参数引用检测通过：作业参数 ${topic} / ${window_size} / ${ckpt_interval} 可用\',\'success\')">参数检测</button>'
    + '<button class="btn btn-sm" onclick="A.stSave(\''+t.id+'\')">保存</button>'
    + '<button class="btn btn-sm" onclick="A.stValidate()">✓ 校验</button>'
    + '<button class="btn btn-sm btn-primary" onclick="A.stDryRun()">▶ 试运行</button>'
    + '</div></div>';
  return head
    + '<div class="etl-main">'
    + '<div id="stVcMount"></div>'
    + '<div class="etl-right">'
    +   '<div class="etl-right-h">验证与测试</div>'
    +   '<div class="etl-right-b">'
    +     '<div id="stValidateBox"><div class="f-help" style="margin-bottom:8px">点击「✓ 校验」检查：孤立节点/断链/流源流输出缺失/CEP 占位。</div></div>'
    +     '<div style="border-top:1px dashed var(--border);margin:10px 0"></div>'
    +     '<b style="font-size:12px">试运行（单批回放）</b>'
    +     '<div style="display:flex;gap:6px;margin:8px 0"><button class="btn btn-sm" onclick="A.stSample()">输入抽样 20 条</button><button class="btn btn-sm btn-primary" onclick="A.stDryRun()">▶ 运行</button></div>'
    +     '<div class="log-box" style="height:180px" id="stRunLog"><span class="lg-info">ℹ 尚未执行。点击「▶ 运行」按拓扑序逐节点回放一批数据。</span></div>'
    +   '</div>'
    + '</div>'
    + '</div>';
});

/* 默认链路：开始→Kafka Source→KeyBy→窗口聚合→数据库 Sink→结束（按作业源/目标命名） */
A.stFlow = function(t){
  if(t.flow) return t.flow;
  var src = t.source||'Kafka: topic_order_pay';
  var topic = src.indexOf(':')>-1? src.slice(src.indexOf(':')+1).trim() : src;
  var sink = t.sink||'Doris: dwd_order_pay_rt';
  var sinkTable = sink.indexOf(':')>-1? sink.slice(sink.indexOf(':')+1).trim() : sink;
  var nodes = [
    {id:'start', name:'开始', type:'START', icon:'▶', color:'#16a34a', x:40, y:200, cat:'系统', summary:'流程入口（固定节点）', cfg:{}},
    {id:'n_src', name:'Kafka Source', type:'kafka_source', icon:'⇊', color:'#0ea5e9', x:190, y:200, cat:'流源', summary:'订阅 '+topic, cfg:{topic:topic, group:'g_'+t.id.toLowerCase(), format:'JSON'}},
    {id:'n_keyby', name:'KeyBy 分流', type:'keyby', icon:'⑃', color:'#8b5cf6', x:350, y:200, cat:'流转换', summary:'按 user_id 哈希分流', cfg:{key:'user_id', para:String(t.parallelism||4)}},
    {id:'n_win', name:'窗口聚合', type:'window', icon:'⏱', color:'#f59e0b', x:510, y:200, cat:'流转换', summary:'滚动窗口 60s · 水位线 4s', cfg:{wtype:'滚动 TUMBLE', size:'60s', step:'60s', wm:'4s'}},
    {id:'n_sink', name:'数据库 Sink', type:'db_sink', icon:'⛃', color:'#16a34a', x:680, y:200, cat:'流输出', summary:'幂等 upsert → '+sinkTable, cfg:{table:sinkTable, mode:'幂等 upsert', pk:'pay_id'}},
    {id:'end', name:'结束', type:'END', icon:'■', color:'#94a3b8', x:850, y:200, cat:'系统', summary:'流程出口（固定节点）', cfg:{}}
  ];
  var edges = [{from:'start', to:'n_src', kind:'flow'}, {from:'n_src', to:'n_keyby', kind:'flow'},
    {from:'n_keyby', to:'n_win', kind:'flow'}, {from:'n_win', to:'n_sink', kind:'flow'}, {from:'n_sink', to:'end', kind:'flow'}];
  return {nodes:nodes, edges:edges};
};

A.stInitVc = function(){
  var t = A._stCur;
  var d = A.stFlow(t);
  A._stVc = VC.create({mount:'stVcMount', nodes:d.nodes, edges:d.edges, palette:A.ST_PALETTE, editable:true, height:620,
    legendExtra:[{c:'#16a34a', t:'开始/结束'}, {c:'#0ea5e9', t:'流源'}, {c:'#16a34a', t:'流输出'}, {c:'#94a3b8', t:'一期暂缓'}],
    onNodeClick:function(n, api){ A.stNodeEdit(n, api); },
    onCanvasChange:function(){ A.stValidate(true); }});
  setTimeout(function(){ A.stValidate(true); }, 60);
};
App.onAfterRender(function(){ if(location.hash.indexOf('#/stream/design/')===0) A.stInitVc(); });

/* 节点配置抽屉（①输入输出 ②算子参数 ③验证与业务逻辑） */
A.stNodeEdit = function(n, api){
  var isSys = n.type==='START'||n.type==='END';
  var fm = A.ST_FORMS[n.type]||{fs:[], help:'节点参数配置'};
  var fHtml = '';
  if(isSys) fHtml = '<div class="empty" style="padding:26px"><span class="e-ico">▣</span><p>系统固定节点，无需算子参数</p></div>';
  else if(!fm.fs.length) fHtml = '<div class="banner banner-warn" style="padding:8px 11px"><span class="b-ico">⚠</span><span style="font-size:12px">'+fm.help+'</span></div>';
  else fm.fs.forEach(function(f){
    var cur = (n.cfg&&n.cfg[f.k])||'';
    if(f.sel) fHtml += UI.fSelect(f.l, 'sf_'+f.k, f.sel.map(function(v){return {v:v, t:v};}), {value:cur||f.sel[0]});
    else fHtml += UI.fInput(f.l, 'sf_'+f.k, {value:cur, ph:f.ph||''});
  });
  UI.drawer({title:'节点配置 - '+n.name, w:'w-lg', body:
    '<div class="tabs" id="stNtTabs"><span class="tab on" onclick="A._stNtTab(this,0)">① 输入输出</span><span class="tab" onclick="A._stNtTab(this,1)">② 算子参数</span><span class="tab" onclick="A._stNtTab(this,2)">③ 验证与业务逻辑</span></div>'
    + '<div id="snt0">'
    + UI.fInput('节点名称', 'sn_name', {value:n.name, req:true})
    + UI.fInput('输入（上游流/字段）', 'sn_in', {value:(n.cfg&&n.cfg['输入'])||'上游节点输出流', disabled:isSys})
    + UI.fInput('输出（下游消费流/表）', 'sn_out', {value:(n.cfg&&n.cfg['输出'])||(n.cat==='流输出'? (A._stCur.sink||''):'透传上游'), disabled:isSys})
    + UI.fInput('字段映射说明', 'sn_io', {value:n.inOut||'', ph:'如：pay_amt(元→分) · 新增 win_start', disabled:isSys})
    + '</div>'
    + '<div id="snt1" style="display:none">'
    + fHtml
    + (isSys? '' : '<div class="f-help">'+fm.help+'</div>')
    + '</div>'
    + '<div id="snt2" style="display:none">'
    + '<div class="banner banner-info"><span class="b-ico">ℹ</span><span>验证规则：①参数完备 ②流字段闭环（Key/时间列存在）③容错配置（Checkpoint/重启策略）齐备。</span></div>'
    + UI.fTextarea('业务逻辑说明', 'sn_logic', {value:(n.cfg&&n.cfg['业务逻辑'])||'', rows:3, ph:'描述该节点业务口径、状态与容错注意事项'})
    + '<button class="btn btn-sm" onclick="UI.toast(\'节点验证通过：参数完备，流字段闭环 ✓\',\'success\')">▶ 验证此节点</button>'
    + '<button class="btn btn-sm" style="margin-left:6px" onclick="AI.show(\'节点「'+UI.esc(n.name)+'」AI 审查：\n· 参数完备性 ✓\n· Key 字段分布均匀，无倾斜风险 ✓\n· 建议 Watermark 容忍 4s 覆盖上游抖动\')">✦ AI 审查</button>'
    + '</div>',
    onOk:function(){
      var cfg = Object.assign({}, n.cfg||{});
      if(!isSys){
        fm.fs.forEach(function(f){ cfg[f.k] = UI.val('sf_'+f.k) || (f.sel? f.sel[0] : ''); });
        cfg['输入'] = UI.val('sn_in'); cfg['输出'] = UI.val('sn_out'); cfg['业务逻辑'] = UI.val('sn_logic');
      }
      api.update(n.id, {name:UI.val('sn_name')||n.name, inOut:UI.val('sn_io'), cfg:cfg, summary:A.stSummary(n, cfg)});
      UI.toast('节点配置已保存，摘要已更新（悬浮可见）', 'success');
    }});
};
A._stNtTab = function(el, i){
  document.querySelectorAll('#stNtTabs .tab').forEach(function(t, idx){ t.classList.toggle('on', idx===i); });
  [0,1,2].forEach(function(x){ var d=document.getElementById('snt'+x); if(d) d.style.display = x===i? '':'none'; });
};
/* 保存后按类型生成摘要（hover 可见） */
A.stSummary = function(n, cfg){
  cfg = cfg||{};
  if(n.type==='START'||n.type==='END') return n.summary;
  var m = A._stMeta[n.type];
  var parts = [];
  (A.ST_SUMKEYS[n.type]||[]).forEach(function(k){ if(cfg[k]) parts.push(cfg[k]); });
  return (m? m.name : n.type) + (parts.length? '：'+parts.join(' · ') : '');
};

/* 链路校验（VC 通用 + 流特有：流源/流输出缺失、CEP 占位） */
A.stValidate = function(quiet){
  if(!A._stVc) return;
  var errs = VC.validate(A._stVc);
  var d = VC.getData(A._stVc);
  var hasSrc = d.nodes.some(function(n){return n.cat==='流源';});
  var hasOut = d.nodes.some(function(n){return n.cat==='流输出';});
  if(d.nodes.length && !hasSrc) errs.push({level:'error', msg:'缺少流源节点（Kafka/CDC/日志/IoT），流作业必须有输入'});
  if(d.nodes.length && !hasOut) errs.push({level:'error', msg:'缺少流输出节点（Kafka/数据库/告警 Sink）'});
  var cep = d.nodes.filter(function(n){return n.type==='cep';});
  if(cep.length) errs.push({level:'warn', msg:'CEP 节点（'+cep.map(function(n){return n.name;}).join('、')+'）一期暂缓，不参与试运行'});
  var box = document.getElementById('stValidateBox'); if(!box) return;
  box.innerHTML = errs.length? errs.map(function(e){
    return '<div class="banner '+(e.level==='error'?'banner-danger':'banner-warn')+'" style="margin-bottom:6px;padding:8px 11px"><span class="b-ico">'+(e.level==='error'?'✗':'⚠')+'</span><span style="font-size:12px">'+UI.esc(e.msg)+'</span></div>';
  }).join('') : '<div class="banner banner-success" style="padding:8px 11px"><span class="b-ico">✓</span><span style="font-size:12px">链路校验通过：流源/流输出齐备，无孤立节点、无断链</span></div>';
  if(!quiet) UI.toast(errs.some(function(e){return e.level==='error';})? '校验发现 '+errs.length+' 个问题':'链路校验通过', errs.length? 'warn':'success');
};

/* 试运行：拓扑排序逐节点点亮 + 右侧日志回放 */
A.stRunMsg = function(n){
  var c = n.cfg||{};
  switch(n.type){
    case 'kafka_source': return '订阅 '+UI.esc(c.topic||'-')+' 拉取 20 条 · group '+(c.group||'-')+' · lag 0';
    case 'cdc_binlog': return '捕获 Binlog 变更 20 条 · 位点前移至最新';
    case 'log_collect': return 'tail 解析 20 行 · '+(c.pattern||'JSON 行');
    case 'iot_access': return '接收设备上报 20 条 · 协议 '+(c.proto||'MQTT');
    case 'keyby': return '按 '+(c.key||'user_id')+' 哈希分区 → 4 子任务 · 分布均衡';
    case 'window': return (c.wtype||'滚动 TUMBLE')+' 窗口 '+(c.size||'60s')+' 触发 · 输出 3 个窗口结果 · wm 推进 '+(c.wm||'4s');
    case 'time_join': return '区间关联命中 18/20 条 · 边界 '+(c.bounds||'-5m ~ +5m');
    case 'state_op': return '状态读写 20 次 · 后端 '+(c.backend||'RocksDB')+' · TTL '+(c.ttl||'24h');
    case 'kafka_sink': return '事务写入 '+(c.topic||'topic_out')+' 20 条 · EXACTLY_ONCE';
    case 'db_sink': return 'Stream Load upsert 20 行 → '+(c.table||'-')+' · 幂等成功';
    case 'alert_sink': return '命中规则 0 条 · 无告警触发';
    case 'checkpoint': return 'Checkpoint ck-12847 完成 · 2.1s · State 186MB';
    case 'savepoint': return 'Savepoint 快照完成 · 写入 '+(c.path||'hdfs:///sp/');
    case 'restart': return '策略 '+(c.strategy||'固定延迟')+' · 当前无故障，无需重启';
    default: return '处理 20 条 · 12ms';
  }
};
A.stDryRun = function(){
  if(!A._stVc){ UI.toast('设计器未就绪','warn'); return; }
  A.stValidate(true);
  var d = VC.getData(A._stVc);
  var log = document.getElementById('stRunLog');
  if(!log) return;
  var order = [];
  (function(){ /* 拓扑排序 */
    var indeg = {}, out = {};
    d.nodes.forEach(function(n){ indeg[n.id]=0; out[n.id]=[]; });
    d.edges.forEach(function(e){ if(out[e.from]!==undefined && out[e.to]!==undefined){ out[e.from].push(e.to); indeg[e.to]++; } });
    var q = d.nodes.filter(function(n){return !indeg[n.id];}).map(function(n){return n.id;});
    while(q.length){ var cur=q.shift(); order.push(cur); (out[cur]||[]).forEach(function(t2){ if(--indeg[t2]===0) q.push(t2); }); }
  })();
  VC.setData(A._stVc, d); /* 此后 d.nodes/d.edges 与画布实例共享引用，可逐节点/逐边点亮 */
  log.innerHTML = '<span class="lg-info">ℹ 流试运行（回放一批 20 条）· '+new Date().toLocaleTimeString()+'</span>';
  order.forEach(function(id, i){
    setTimeout(function(){
      var n = d.nodes.find(function(x){return x.id===id;});
      if(!n) return;
      if(n.type==='cep'){
        log.insertAdjacentHTML('beforeend','<br><span class="lg-warn">⊘ ['+String(i+1).padStart(2,'0')+'] '+UI.esc(n.name)+' 跳过（CEP 一期暂缓，不参与试运行）</span>');
      } else {
        VC.updateNode(A._stVc, id, {status:'success'});
        d.edges.forEach(function(e){ if(e.from===id) e.run = true; });
        log.insertAdjacentHTML('beforeend','<br><span class="lg-ok">✓ ['+String(i+1).padStart(2,'0')+'] '+UI.esc(n.name)+' — '+A.stRunMsg(n)+'</span>');
      }
      log.scrollTop = log.scrollHeight;
    }, 350*(i+1));
  });
  if(!order.length) return;
  setTimeout(function(){
    log.insertAdjacentHTML('beforeend','<br><span class="lg-ok">✔ 试运行成功：端到端延迟 380ms · Watermark 2026-09-12 22:28:36（延迟 4s）· Checkpoint EXACTLY_ONCE ✓</span>');
    log.scrollTop = log.scrollHeight;
  }, 350*(order.length+1));
};

/* 输入抽样（Topic 最新 20 条，确定性生成避免重复计算） */
A.stSample = function(){
  var rows = [];
  for(var i=1;i<=20;i++){
    rows.push({pay_id:20260911220300+i, pay_time:'2026-09-12 22:2'+Math.floor((i-1)/10)+':'+String((i*3)%60).padStart(2,'0'),
      order_no:'SO2026'+String(9100+i), user_id:'U'+String(1000+i*7),
      amount:i===4? -10.00 : +(((i*127)%9800)/10+8).toFixed(2),
      ch:['WECHAT','ALIPAY','UNIONPAY','BANK'][i%4], st:i%9===0? 0:1});
  }
  UI.drawer({title:'输入抽样（Topic 最新 20 条）', w:'w-xl', body:
    UI.tbl({id:'t_stsmp', rowKey:'pay_id', pageSize:10, searchKeys:['pay_id','order_no'],
      data:function(){ return rows; },
      cols:[{t:'pay_id',k:'pay_id',render:function(r){return '<span class="mono">'+r.pay_id+'</span>';}},
        {t:'pay_time',k:'pay_time',render:function(r){return '<span class="mono">'+r.pay_time+'</span>';}},
        {t:'order_no',k:'order_no',render:function(r){return '<span class="mono">'+r.order_no+'</span>';}},
        {t:'user_id',k:'user_id'},{t:'pay_amount',k:'amount',render:function(r){return '<span class="mono" style="color:'+(r.amount<0?'var(--danger)':'inherit')+'">'+r.amount.toFixed(2)+'</span>';}},
        {t:'pay_channel',k:'ch'},{t:'pay_status',k:'st',render:function(r){return r.st? st('success'):st('failed');}}],
      ops:null})});
};

/* 保存设计稿：写回 job.flow（供下次进入还原） */
A.stSave = function(id){
  var t = id? DB.streamJobs.find(function(x){return x.id===id;}) : A._stCur;
  if(!t) return;
  if(A._stVc){
    var d = VC.getData(A._stVc);
    t.flow = d;
    t.ops = d.nodes.filter(function(n){return n.cat!=='系统' && n.type!=='cep';}).map(function(n){ return {id:n.id, type:n.type, name:n.name, cfg:n.cfg||{}}; });
  }
  UI.toast('已保存流设计稿（节点 '+((t.flow&&t.flow.nodes)||[]).length+' 个）', 'success');
};
})();
