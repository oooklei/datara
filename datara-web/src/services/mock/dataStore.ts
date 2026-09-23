/**
 * dataStore — data.js 蓝图全量迁移（Wave 0 todo 3）
 * 来源: prototype/assets/data.js（ST L9-35 / MENUS L41-114 / DB L117-713 + lineageGraph L716-739）
 * 逐字迁移，不做业务值改写。IDataStore 内存实现 + localStorage 兜底（key: datara.db.<collection>）。
 */
import type {
  StDict,
  MenuGroup,
  CollectionKey,
  IDataStore,
} from '../types'
export const ST: StDict = {
  draft:      {label:'草稿',     cls:'st-gray'},
  published:  {label:'已发布',   cls:'st-green'},
  disabled:   {label:'已停用',   cls:'st-gray'},
  enabled:    {label:'已启用',   cls:'st-green'},
  approving:  {label:'审批中',   cls:'st-orange'},
  review:     {label:'评审中',   cls:'st-orange'},
  abolished:  {label:'已废止',   cls:'st-red'},
  online:     {label:'已上线',   cls:'st-green'},
  offline:    {label:'已下线',   cls:'st-gray'},
  running:    {label:'运行中',   cls:'st-blue'},
  waiting:    {label:'等待中',   cls:'st-gray'},
  success:    {label:'成功',     cls:'st-green'},
  failed:     {label:'失败',     cls:'st-red'},
  paused:     {label:'已暂停',   cls:'st-orange'},
  stopped:    {label:'已停止',   cls:'st-gray'},
  skipped:    {label:'已跳过',   cls:'st-purple'},
  diff:       {label:'数据差异', cls:'st-orange'},
  killed:     {label:'已终止',   cls:'st-red'},
  checking:   {label:'检查中',   cls:'st-blue'},
  pass:       {label:'通过',     cls:'st-green'},
  reject:     {label:'驳回',     cls:'st-red'},
  pending:    {label:'待处理',   cls:'st-orange'},
  fixed:      {label:'已修复',   cls:'st-green'},
  ignored:    {label:'已忽略',   cls:'st-gray'},
  recovered:  {label:'已恢复',   cls:'st-blue'}
};

export const MENUS: MenuGroup[] = [
  {group:'总览', items:[
    {id:'dashboard', icon:'◆', label:'工作台', path:'#/dashboard'}
  ]},
  {group:'数据集成', items:[
    {id:'m03', icon:'⛁', label:'数据源管理', path:'#/ds/list'}
  ]},
  {group:'数据开发', items:[
    {id:'m04', icon:'▤', label:'数仓建模', path:'#/model/list'},
    {id:'m11', icon:'⌨', label:'数据开发IDE', path:'#/ide'},
    {id:'m13', icon:'⑃', label:'DAG工作流', path:'#/dag/list', children:[
      {label:'工作流定义', path:'#/dag/list'},
      {label:'运行实例', path:'#/dag/runs'},
      {label:'依赖管理', path:'#/dag/depend'},
      {label:'告警与SLA', path:'#/dag/alarm'}
    ]},
    {id:'m14', icon:'⌘', label:'脚本任务', path:'#/script/list', children:[
      {label:'脚本库', path:'#/script/list'},
      {label:'环境与依赖', path:'#/script/env'},
      {label:'远程执行(SSH)', path:'#/script/remote'}
    ]},
    {id:'m12', icon:'⚑', label:'参数配置', path:'#/param/global', children:[
      {label:'全局参数', path:'#/param/global'},
      {label:'内置时间参数', path:'#/param/builtin'},
      {label:'环境参数组', path:'#/param/env'},
      {label:'引用检测与预览', path:'#/param/tools'}
    ]}
  ]},
  {group:'数据治理', items:[
    {id:'m07', icon:'✓', label:'数据质量', path:'#/qc/score', children:[
      {label:'质量评分卡', path:'#/qc/score'},
      {label:'质量规则', path:'#/qc/rule'},
      {label:'检查任务', path:'#/qc/task'},
      {label:'异常数据核查', path:'#/qc/exception'},
      {label:'质量报告', path:'#/qc/report'},
      {label:'质量告警', path:'#/qc/alarm'}
    ]},
    {id:'m09', icon:'☰', label:'元数据管理', path:'#/meta/catalog', children:[
      {label:'元数据目录', path:'#/meta/catalog'},
      {label:'血缘分析', path:'#/meta/lineage'},
      {label:'数据资产地图', path:'#/meta/map'},
      {label:'标签管理', path:'#/meta/tag'}
    ]},
    {id:'m10', icon:'⌇', label:'数据标准', path:'#/std/element', children:[
      {label:'数据元标准', path:'#/std/element'},
      {label:'代码标准', path:'#/std/code'},
      {label:'命名规范', path:'#/std/naming'},
      {label:'标准映射与合规', path:'#/std/mapping'},
      {label:'标准审批', path:'#/std/approval'}
    ]},
    {id:'m10i', icon:'✦', label:'指标管理', path:'#/ind/list', children:[
      {label:'指标目录', path:'#/ind/list'},
      {label:'指标看板', path:'#/ind/board'},
      {label:'一致性检查', path:'#/ind/consistency'}
    ]}
  ]},
  {group:'部署运维', items:[
    {id:'m16', icon:'⛅', label:'一键部署', path:'#/dep/center', children:[
      {label:'部署中心', path:'#/dep/center'},
      {label:'集群监控', path:'#/dep/monitor'},
      {label:'组件日志', path:'#/dep/log'},
      {label:'告警管理', path:'#/dep/alarm'},
      {label:'运维操作', path:'#/dep/ops'}
    ]}
  ]}
];

export const DB = {
  env: 'prod',
  user: {name:'王工', role:'数据平台管理员', clearance:'绝密'},

  /* ===== M15 数据安全 ===== */
  users: [
    {id:'U001', name:'王工', role:'admin',   roleName:'数据平台管理员', clearance:'绝密', domains:[], status:'enabled', lastLogin:'2026-09-14 08:30'},
    {id:'U002', name:'李工', role:'dev',     roleName:'数据开发',       clearance:'机密', domains:['交易域','公共'], status:'enabled', lastLogin:'2026-09-13 19:05'},
    {id:'U003', name:'张工', role:'dev',     roleName:'数据开发',       clearance:'内部', domains:['商品域'], status:'enabled', lastLogin:'2026-09-13 15:42'},
    {id:'U004', name:'赵工', role:'analyst', roleName:'数据分析',       clearance:'机密', domains:['财务域','经营域'], status:'enabled', lastLogin:'2026-09-12 17:20'},
    {id:'U005', name:'访客', role:'viewer',  roleName:'只读访客',       clearance:'公开', domains:[], status:'enabled', lastLogin:'2026-09-10 10:11'}
  ],
  maskRules: [
    {id:'MK01', field:'phone',       type:'手机号',  strategy:'掩码（保留前3后4）', scope:'全库 sample 预览', enabled:true},
    {id:'MK02', field:'id_card',     type:'身份证号', strategy:'掩码（保留前6后4）', scope:'全库 sample 预览', enabled:true},
    {id:'MK03', field:'bank_card',   type:'银行卡号', strategy:'掩码（保留后4位）',  scope:'全库 sample 预览', enabled:true},
    {id:'MK04', field:'user_name',   type:'姓名',    strategy:'替换（姓*）',       scope:'元数据目录', enabled:true},
    {id:'MK05', field:'pay_amount',  type:'金额',    strategy:'哈希（SM4）',       scope:'API 导出', enabled:false}
  ],
  accessLogs: [
    {id:'AL001', user:'王工', action:'预览', target:'dwd_order_pay_detail', rows:3, ts:'2026-09-14 09:12', result:'允许', reason:'密级（机密）≤ 许可（绝密）'},
    {id:'AL002', user:'赵工', action:'预览', target:'ods_oracle_gl_voucher', rows:0, ts:'2026-09-14 08:47', result:'拒绝', reason:'密级（绝密）＞ 许可（机密）'},
    {id:'AL003', user:'李工', action:'查询', target:'dim_user', rows:1250000, ts:'2026-09-13 19:05', result:'允许', reason:'公共域已授权'},
    {id:'AL004', user:'张工', action:'导出', target:'ods_gdb_biz_user_info', rows:0, ts:'2026-09-13 15:42', result:'拒绝', reason:'密级（机密）＞ 许可（内部）'},
    {id:'AL005', user:'访客', action:'预览', target:'ads_kpi_report', rows:1, ts:'2026-09-12 10:30', result:'允许', reason:'公开'},
    {id:'AL006', user:'赵工', action:'查询', target:'dws_pay_summary_daily', rows:1860, ts:'2026-09-12 09:15', result:'允许', reason:'交易域已授权'}
  ],
  notifications: [
    {id:1, icon:'⛔', cls:'err', title:'DAG工作流「订单主题日增」实例 #R20260911 失败', desc:'节点 dws_pay_summary_daily 执行失败，等待断点恢复', time:'2026-09-12 07:32'},
    {id:2, icon:'✓', cls:'ok', title:'批量同步批次 SYNC_20260911_001 完成', desc:'25张表：23成功 1差异 1失败，详见核对报告', time:'2026-09-12 03:20'},
    {id:3, icon:'⚑', cls:'warn', title:'质量告警：dwd_order_pay_detail.pay_amount 存在负值', desc:'规则 QC-R-012 范围检查，异常 12 行', time:'2026-09-12 02:15'}
  ],
  /* 告警通知渠道配置（邮件 SMTP + 短信网关；全平台告警规则共用；飞书/钉钉规划中）
   * 见 DeployAlarmView 通知渠道抽屉：配置保存与发送测试均读写本集合 */
  channelCfg: {
    mail: { host:'smtp.datara.cn', port:465, ssl:true, account:'notify@datara.cn', password:'******', sender:'notify@datara.cn' },
    sms:  { provider:'阿里云', accessKey:'LTAI5t***', secret:'******', sign:'数据治理平台', template:'SMS_466150001' }
  },

  /* ===== M03 数据源 ===== */
  dsTypes: [
    {name:'万里 GreatDB',   code:'greatdb',  group:'国产数据库', xc:true,  port:3306,  color:'#c2410c'},
    {name:'华为 GaussDB',   code:'gaussdb',  group:'国产数据库', xc:true,  port:8000,  color:'#9333ea'},
    {name:'达梦 DM8',       code:'dameng',   group:'国产数据库', xc:true,  port:5236,  color:'#dc2626'},
    {name:'MySQL',          code:'mysql',    group:'关系型',    xc:false, port:3306,  color:'#0891b2'},
    {name:'Oracle',         code:'oracle',   group:'关系型',    xc:false, port:1521,  color:'#e11d48'},
    {name:'Apache Doris',   code:'doris',    group:'数仓引擎',  xc:false, port:9030,  color:'#2563eb'},
    {name:'Hive',           code:'hive',     group:'数仓引擎',  xc:false, port:10000, color:'#f59e0b'},
    {name:'Kafka',          code:'kafka',    group:'消息队列',  xc:false, port:9092,  color:'#0d9488'},
    {name:'PostgreSQL',     code:'postgres', group:'关系型',    xc:false, port:5432,  color:'#336791'},
    {name:'SQL Server',     code:'mssql',    group:'关系型',    xc:false, port:1433,  color:'#a91d22'},
    {name:'人大金仓 Kingbase', code:'kingbase', group:'国产数据库', xc:true, port:54321, color:'#c8102e'},
    {name:'HBase',          code:'hbase',    group:'数仓引擎',  xc:false, port:16020, color:'#f97316'},
    {name:'StarRocks',      code:'starrocks', group:'数仓引擎', xc:false, port:9030,  color:'#4f46e5'},
    {name:'MongoDB',        code:'mongo',    group:'NoSQL',     xc:false, port:27017, color:'#47a248'},
    {name:'Redis',          code:'redis',    group:'NoSQL',     xc:false, port:6379,  color:'#d82c20'},
    {name:'Elasticsearch',  code:'es',       group:'NoSQL',     xc:false, port:9200,  color:'#f5bd4f'},
    {name:'RocketMQ',       code:'rocketmq', group:'消息队列',  xc:false, port:9876,  color:'#f59e0b'},
    {name:'RabbitMQ',       code:'rabbitmq', group:'消息队列',  xc:false, port:5672,  color:'#ff6600'},
    {name:'CSV文件',        code:'file_csv',    group:'文件',    xc:false, port:0, color:'#64748b'},
    {name:'JSON文件',       code:'file_json',   group:'文件',    xc:false, port:0, color:'#64748b'},
    {name:'Parquet文件',    code:'file_parquet', group:'文件',   xc:false, port:0, color:'#64748b'},
    {name:'Excel文件',      code:'file_excel',  group:'文件',    xc:false, port:0, color:'#217346'},
    {name:'TXT文件',        code:'file_txt',    group:'文件',    xc:false, port:0, color:'#64748b'},
    {name:'RESTful API',    code:'api_rest',    group:'API接口', xc:false, port:0, color:'#7c3aed'},
    {name:'WebService',     code:'api_ws',      group:'API接口', xc:false, port:0, color:'#7c3aed'}
  ],
  datasources: [
    {id:'DS001', name:'万里GreatDB-生产业务库', type:'万里 GreatDB', host:'192.168.10.21', port:3306, db:'gdb_biz', user:'datara_ro', pwd:'******',
     env:'生产', group:'交易域', tags:['核心','高优先'], pool:{max:20,minIdle:2,idle:600,timeout:30}, status:'enabled', owner:'王工', createdAt:'2026-08-20 10:12', latency:12, health:'健康'},
    {id:'DS002', name:'达梦DM8-经营管理库', type:'达梦 DM8', host:'192.168.10.35', port:5236, db:'DM_MGMT', user:'mgmt_read', pwd:'******',
     env:'生产', group:'经营域', tags:['核心'], pool:{max:15,minIdle:2,idle:600,timeout:30}, status:'enabled', owner:'李工', createdAt:'2026-08-21 14:03', latency:18, health:'健康'},
    {id:'DS003', name:'MySQL-业务测试库', type:'MySQL', host:'192.168.20.11', port:3306, db:'biz_test', user:'test_ro', pwd:'******',
     env:'测试', group:'交易域', tags:['联调'], pool:{max:10,minIdle:1,idle:300,timeout:20}, status:'enabled', owner:'张工', createdAt:'2026-08-23 09:40', latency:5, health:'健康'},
    {id:'DS004', name:'Oracle-ERP系统', type:'Oracle', host:'192.168.10.60', port:1521, db:'ORCL', user:'erp_read', pwd:'******',
     env:'生产', group:'财务域', tags:['核心','涉密'], pool:{max:10,minIdle:1,idle:600,timeout:60}, status:'enabled', owner:'赵工', createdAt:'2026-08-25 16:20', latency:35, health:'延迟偏高'},
    {id:'DS005', name:'GaussDB-汇聚数仓', type:'华为 GaussDB', host:'192.168.30.8', port:8000, db:'gdb_dw', user:'dw_admin', pwd:'******',
     env:'生产', group:'数仓', tags:['汇聚层'], pool:{max:30,minIdle:5,idle:600,timeout:30}, status:'enabled', owner:'王工', createdAt:'2026-08-26 11:05', latency:22, health:'健康'},
    {id:'DS006', name:'Doris-分析集群', type:'Apache Doris', host:'192.168.30.20', port:9030, db:'dw_olap', user:'olap', pwd:'******',
     env:'生产', group:'数仓', tags:['OLAP'], pool:{max:30,minIdle:5,idle:600,timeout:30}, status:'enabled', owner:'王工', createdAt:'2026-08-27 15:30', latency:9, health:'健康'},
    {id:'DS007', name:'Kafka-实时消息集群', type:'Kafka', host:'192.168.30.41:9092,192.168.30.42:9092', port:9092, db:'-', user:'-', pwd:'-',
     env:'生产', group:'消息', tags:['实时'], pool:{max:5,minIdle:1,idle:300,timeout:10}, status:'disabled', owner:'刘工', createdAt:'2026-08-28 10:00', latency:3, health:'健康'},
    {id:'DS008', name:'万里GreatDB-开发环境库', type:'万里 GreatDB', host:'192.168.40.21', port:3306, db:'gdb_dev', user:'dev', pwd:'******',
     env:'开发', group:'交易域', tags:['联调'], pool:{max:5,minIdle:1,idle:300,timeout:15}, status:'enabled', owner:'张工', createdAt:'2026-09-01 09:15', latency:8, health:'健康'},
    {id:'DS009', name:'PostgreSQL-日志分析库', type:'PostgreSQL', host:'192.168.30.51', port:5432, db:'log_analysis', user:'log_ro', pwd:'******',
     env:'生产', group:'数据服务', tags:['分析'], pool:{max:15,minIdle:2,idle:600,timeout:30}, status:'enabled', owner:'刘工', createdAt:'2026-09-05 11:20', latency:15, health:'健康'},
    {id:'DS010', name:'Redis-实时缓存集群', type:'Redis', host:'192.168.30.61', port:6379, db:'0', user:'default', pwd:'******',
     env:'生产', group:'消息', tags:['缓存','实时'], pool:{max:10,minIdle:1,idle:300,timeout:10}, status:'enabled', owner:'刘工', createdAt:'2026-09-05 11:20', latency:2, health:'健康'}
  ],

  /* ===== M04 数仓模型 ===== */
  dwLayers: [
    {code:'ODS', name:'原始数据层', desc:'从数据源原样同步，不做加工', color:'#0891b2', rule:'ods_源库名_源表名，保留原始字段'},
    {code:'DWD', name:'明细数据层', desc:'清洗、标准化、维度退化后的明细事实表', color:'#1668dc', rule:'dwd_业务_过程，一个过程一张表'},
    {code:'DWS', name:'汇总数据层', desc:'按主题、维度进行轻度/重度汇总聚合', color:'#7c3aed', rule:'dws_主题_粒度，预聚合指标'},
    {code:'ADS', name:'应用数据层', desc:'面向应用的宽表/指标结果表', color:'#16a34a', rule:'ads_应用_场景，直接服务报表'},
    {code:'DIM', name:'维度层', desc:'公共维度表', color:'#d97706', rule:'dim_维度名，全局唯一'},
    {code:'TMP', name:'临时层', desc:'临时表/中间结果，跑批过程中产生，跑完即清理', color:'#64748b', rule:'tmp_业务_用途，跑完即清理'}
  ],
  models: [
    {id:'MD001', name:'用户信息原始表', code:'ods_gdb_biz_user_info', layer:'ODS', engine:'Apache Doris', type:'明细表', status:'published',
     fields:[
       {n:'user_id',t:'BIGINT',len:'',pk:true,pkPart:false,cmt:'用户ID',def:''},
       {n:'user_name',t:'VARCHAR',len:100,pk:false,pkPart:false,cmt:'用户姓名',def:''},
       {n:'phone',t:'VARCHAR',len:20,pk:false,pkPart:false,cmt:'手机号',def:''},
       {n:'gender',t:'CHAR',len:1,pk:false,pkPart:false,cmt:'性别 M/F',def:'M'},
       {n:'create_time',t:'DATETIME',len:'',pk:false,pkPart:false,cmt:'创建时间',def:''},
       {n:'dt',t:'DATE',len:'',pk:false,pkPart:true,cmt:'分区字段',def:''}],
     version:3, owner:'王工', bizDomain:'交易域', updatedAt:'2026-09-10 15:20',
     versions:[{v:3,date:'2026-09-10 15:20',author:'王工',note:'增加gender字段',status:'当前版本'},{v:2,date:'2026-08-30 11:02',author:'李工',note:'phone长度20→100回退调整',status:'历史'},{v:1,date:'2026-08-22 09:41',author:'王工',note:'初版，逆向工程生成',status:'历史'}]},
    {id:'MD002', name:'订单支付明细表', code:'dwd_order_pay_detail', layer:'DWD', engine:'Apache Doris', type:'事实表', status:'published',
     fields:[
       {n:'pay_id',t:'BIGINT',len:'',pk:true,pkPart:false,cmt:'支付单号',def:''},
       {n:'order_id',t:'BIGINT',len:'',pk:false,pkPart:false,cmt:'订单ID',def:''},
       {n:'user_id',t:'BIGINT',len:'',pk:false,pkPart:false,cmt:'用户ID',def:''},
       {n:'pay_amount',t:'DECIMAL',len:'(18,2)',pk:false,pkPart:false,cmt:'支付金额',def:'0.00'},
       {n:'pay_status',t:'TINYINT',len:'',pk:false,pkPart:false,cmt:'支付状态 1成功 0失败',def:''},
       {n:'pay_channel',t:'VARCHAR',len:20,pk:false,pkPart:false,cmt:'支付渠道',def:''},
       {n:'dt',t:'DATE',len:'',pk:false,pkPart:true,cmt:'分区字段',def:''}],
     version:5, owner:'李工', bizDomain:'交易域', updatedAt:'2026-09-11 10:05',
     versions:[{v:5,date:'2026-09-11 10:05',author:'李工',note:'增加pay_channel字段（标准映射合规整改）',status:'当前版本'},{v:4,date:'2026-09-02 17:10',author:'李工',note:'pay_amount精度调整为(18,2)',status:'历史'},{v:1,date:'2026-08-24 14:22',author:'王工',note:'初版',status:'历史'}]},
    {id:'MD003', name:'支付主题日汇总', code:'dws_pay_summary_daily', layer:'DWS', engine:'Apache Doris', type:'汇总表', status:'published',
     fields:[
       {n:'stat_date',t:'DATE',len:'',pk:true,pkPart:true,cmt:'统计日期',def:''},
       {n:'channel',t:'VARCHAR',len:20,pk:true,pkPart:false,cmt:'支付渠道',def:''},
       {n:'pay_user_cnt',t:'BIGINT',len:'',pk:false,pkPart:false,cmt:'支付用户数',def:'0'},
       {n:'pay_order_cnt',t:'BIGINT',len:'',pk:false,pkPart:false,cmt:'支付订单数',def:'0'},
       {n:'pay_amount_sum',t:'DECIMAL',len:'(18,2)',pk:false,pkPart:false,cmt:'支付金额合计',def:'0.00'}],
     version:2, owner:'李工', bizDomain:'交易域', updatedAt:'2026-09-08 11:30',
     versions:[{v:2,date:'2026-09-08 11:30',author:'李工',note:'增加channel维度',status:'当前版本'},{v:1,date:'2026-08-26 10:15',author:'李工',note:'初版',status:'历史'}]},
    {id:'MD004', name:'经营KPI报表宽表', code:'ads_kpi_report', layer:'ADS', engine:'Apache Doris', type:'宽表', status:'published',
     fields:[
       {n:'stat_date',t:'DATE',len:'',pk:true,pkPart:true,cmt:'统计日期',def:''},
       {n:'gmv',t:'DECIMAL',len:'(18,2)',pk:false,pkPart:false,cmt:'成交额',def:'0.00'},
       {n:'pay_user_cnt',t:'BIGINT',len:'',pk:false,pkPart:false,cmt:'支付用户数',def:'0'},
       {n:'pay_amount_7d',t:'DECIMAL',len:'(18,2)',pk:false,pkPart:false,cmt:'近7天支付金额',def:'0.00'}],
     version:1, owner:'赵工', bizDomain:'经营域', updatedAt:'2026-09-05 09:12',
     versions:[{v:1,date:'2026-09-05 09:12',author:'赵工',note:'初版，物理化建表成功',status:'当前版本'}]},
    {id:'MD005', name:'用户维度表', code:'dim_user', layer:'DIM', engine:'Apache Doris', type:'维度表', status:'published',
     fields:[
       {n:'user_id',t:'BIGINT',len:'',pk:true,pkPart:false,cmt:'用户ID',def:''},
       {n:'user_name',t:'VARCHAR',len:100,pk:false,pkPart:false,cmt:'姓名',def:''},
       {n:'org_name',t:'VARCHAR',len:200,pk:false,pkPart:false,cmt:'所属机构',def:''},
       {n:'user_level',t:'VARCHAR',len:10,pk:false,pkPart:false,cmt:'用户等级 01普通/02VIP/03SVIP',def:'01'}],
     version:2, owner:'王工', bizDomain:'公共', updatedAt:'2026-09-06 16:40',
     versions:[{v:2,date:'2026-09-06 16:40',author:'王工',note:'user_level对齐代码标准C-003',status:'当前版本'},{v:1,date:'2026-08-25 13:00',author:'王工',note:'初版',status:'历史'}]},
    {id:'MD006', name:'商品信息原始表', code:'ods_mysql_product_info', layer:'ODS', engine:'Apache Doris', type:'明细表', status:'draft',
     fields:[
       {n:'product_id',t:'BIGINT',len:'',pk:true,pkPart:false,cmt:'商品ID',def:''},
       {n:'product_name',t:'VARCHAR',len:200,pk:false,pkPart:false,cmt:'商品名称',def:''},
       {n:'price',t:'DECIMAL',len:'(12,2)',pk:false,pkPart:false,cmt:'价格',def:'0.00'},
       {n:'dt',t:'DATE',len:'',pk:false,pkPart:true,cmt:'分区字段',def:''}],
     version:1, owner:'张工', bizDomain:'商品域', updatedAt:'2026-09-11 14:50',
     versions:[{v:1,date:'2026-09-11 14:50',author:'张工',note:'从MySQL测试库逆向工程导入',status:'当前版本'}]}
  ],
  engineTypes: [
    {name:'Apache Doris', ddl:'MySQL兼容DDL', xc:false},
    {name:'Hive/Spark SQL', ddl:'HiveQL DDL', xc:false},
    {name:'达梦 DM8', ddl:'Oracle兼容DDL', xc:true},
    {name:'人大金仓 Kingbase', ddl:'Oracle兼容DDL', xc:true},
    {name:'GaussDB DWS', ddl:'PostgreSQL兼容DDL', xc:true},
    {name:'万里 GreatDB', ddl:'MySQL兼容DDL', xc:true},
    {name:'Hudi/Iceberg', ddl:'Spark/Flink DDL', xc:false}
  ],

  /* ===== M05 批处理/同步 ===== */
  syncBatches: [
    {id:'SYNC_20260911_001', srcDs:'DS003', srcName:'MySQL-业务测试库', target:'Doris-分析集群', mode:'首次全量+后续增量', strategy:'自动建表+按天分区',
     total:25, ok:23, diff:1, fail:1, srcRows:12500000, tgtRows:12498000, status:'diff',
     startAt:'2026-09-12 02:00:00', endAt:'2026-09-12 03:20:00', cron:'0 0 2 * * ?', concurrency:5, retry:2,
     logs:[
       {st:'user_info', tt:'ods_mysql_user_info', sc:1250000, tc:1250000, dc:0, status:'success', dur:'45s', partition:'2026-09-11'},
       {st:'order_info', tt:'ods_mysql_order_info', sc:5000000, tc:5000000, dc:0, status:'success', dur:'120s', partition:'2026-09-11'},
       {st:'product_info', tt:'ods_mysql_product_info', sc:80000, tc:78000, dc:2000, status:'diff', dur:'15s', partition:'2026-09-11'},
       {st:'user_address', tt:'ods_mysql_user_address', sc:0, tc:0, dc:0, status:'failed', dur:'8s', partition:'2026-09-11'},
       {st:'pay_log', tt:'ods_mysql_pay_log', sc:3200000, tc:3200000, dc:0, status:'success', dur:'95s', partition:'2026-09-11'},
       {st:'member_level', tt:'ods_mysql_member_level', sc:120000, tc:120000, dc:0, status:'success', dur:'22s', partition:'2026-09-11'},
       {st:'coupon_record', tt:'ods_mysql_coupon_record', sc:890000, tc:890000, dc:0, status:'success', dur:'60s', partition:'2026-09-11'}
     ]},
    {id:'SYNC_20260910_001', srcDs:'DS004', srcName:'Oracle-ERP系统', target:'Doris-分析集群', mode:'全量同步', strategy:'自动建表+按天分区',
     total:8, ok:8, diff:0, fail:0, srcRows:2340000, tgtRows:2340000, status:'success',
     startAt:'2026-09-11 02:00:00', endAt:'2026-09-11 02:41:00', cron:'0 0 2 * * ?', concurrency:5, retry:2,
     logs:[
       {st:'GL_VOUCHER', tt:'ods_oracle_gl_voucher', sc:560000, tc:560000, dc:0, status:'success', dur:'55s'},
       {st:'AR_CUSTOMER', tt:'ods_oracle_ar_customer', sc:43000, tc:43000, dc:0, status:'success', dur:'12s'}
     ]},
    {id:'SYNC_20260910_002', srcDs:'DS001', srcName:'万里GreatDB-生产业务库', target:'Doris-分析集群', mode:'首次全量+后续增量', strategy:'自动建表+按天分区',
     total:42, ok:42, diff:0, fail:0, srcRows:8800000, tgtRows:8800000, status:'success',
     startAt:'2026-09-11 01:00:00', endAt:'2026-09-11 02:05:00', cron:'0 0 1 * * ?', concurrency:5, retry:2,
     logs:[
       {st:'trade_order', tt:'ods_gdb_biz_trade_order', sc:4100000, tc:4100000, dc:0, status:'success', dur:'150s'},
       {st:'pay_record', tt:'ods_gdb_biz_pay_record', sc:2600000, tc:2600000, dc:0, status:'success', dur:'110s'}
     ]},
    {id:'SYNC_20260912_001', srcDs:'DS002', srcName:'达梦DM8-经营管理库', target:'GaussDB-汇聚数仓', mode:'增量同步', strategy:'仅同步不建表+按天分区',
     total:6, ok:2, diff:0, fail:0, srcRows:0, tgtRows:0, status:'running',
     startAt:'2026-09-12 22:00:00', endAt:'-', cron:'0 0 22 * * ?', concurrency:3, retry:3,
     logs:[
       {st:'BUDGET_YEAR', tt:'ods_dm_budget_year', sc:12500, tc:12500, dc:0, status:'success', dur:'18s'},
       {st:'KPI_MONTH', tt:'ods_dm_kpi_month', sc:8600, tc:8600, dc:0, status:'success', dur:'11s'},
       {st:'ORG_INFO', tt:'ods_dm_org_info', sc:0, tc:0, dc:0, status:'waiting', dur:'-'}
     ]}
  ],
  /* 同步批次历史趋势（近7天，确定性写死值，供批次看板合并展示） */
  syncHistory: [
    {date:'2026-09-05', rows:10800000, dur:'3h05m', ok:23, fail:1},
    {date:'2026-09-06', rows:11200000, dur:'2h55m', ok:24, fail:0},
    {date:'2026-09-07', rows:10900000, dur:'3h02m', ok:22, fail:1},
    {date:'2026-09-08', rows:11800000, dur:'3h10m', ok:25, fail:0},
    {date:'2026-09-09', rows:11500000, dur:'3h18m', ok:23, fail:0},
    {date:'2026-09-10', rows:12100000, dur:'2h50m', ok:24, fail:1},
    {date:'2026-09-11', rows:12500000, dur:'3h20m', ok:23, fail:0}
  ],
  etlTasks: [
    {id:'ETL001', name:'清洗支付明细', code:'etl_dwd_order_pay_clean', type:'可视化ETL', status:'published', owner:'李工',
     ops:[
       {id:'op1', type:'输入源', name:'读取ODS订单', cfg:'ods_gdb_biz_trade_order'},
       {id:'op2', type:'过滤', name:'过滤无效订单', cfg:"pay_status IS NOT NULL AND amount > 0"},
       {id:'op3', type:'Join', name:'关联用户维度', cfg:'LEFT JOIN dim_user ON user_id'},
       {id:'op4', type:'表达式', name:'计算实付金额', cfg:'pay_amount = amount - discount'},
       {id:'op5', type:'去重', name:'按pay_id去重', cfg:'DISTINCT pay_id'},
       {id:'op6', type:'输出', name:'写入DWD', cfg:'dwd_order_pay_detail（覆盖分区 dt=${biz_date}）'}
     ], cron:'0 30 2 * * ?', lastRun:'success', updatedAt:'2026-09-10 11:20'},
    {id:'ETL002', name:'支付主题日汇总SQL', code:'etl_dws_pay_summary', type:'SQL任务', status:'published', owner:'李工',
     sql:"INSERT OVERWRITE TABLE dws_pay_summary_daily PARTITION (dt='${biz_date}')\nSELECT stat_date, channel,\n       COUNT(DISTINCT user_id) AS pay_user_cnt,\n       COUNT(1) AS pay_order_cnt,\n       SUM(pay_amount) AS pay_amount_sum\nFROM dwd_order_pay_detail\nWHERE pay_status = 1 AND dt = '${biz_date}'\nGROUP BY stat_date, channel;",
     cron:'0 0 3 * * ?', lastRun:'success', updatedAt:'2026-09-08 09:30'},
    {id:'ETL003', name:'经营KPI宽表加工', code:'etl_ads_kpi', type:'SQL任务', status:'published', owner:'赵工',
     sql:"INSERT OVERWRITE TABLE ads_kpi_report PARTITION (dt='${biz_date}')\nSELECT ...",
     cron:'0 30 3 * * ?', lastRun:'success', updatedAt:'2026-09-05 15:00'},
    {id:'ETL004', name:'ERP财务凭证清洗', code:'etl_dwd_gl_voucher', type:'脚本任务', status:'draft', owner:'赵工',
     scriptLang:'Python', script:'import pandas as pd\n# 读取ODS凭证数据，清洗摘要字段\n...',
     cron:'', lastRun:'-', updatedAt:'2026-09-11 16:40'}
  ],

  /* ===== M06 流处理 ===== */
  streamJobs: [
    {id:'SJ001', name:'订单支付实时入仓', type:'Flink SQL', source:'Kafka: topic_order_pay', sink:'Doris: dwd_order_pay_rt', status:'running',
     checkpoint:{interval:'60s', mode:'Exactly-Once', backend:'RocksDB', lastOk:'2026-09-12 22:28:40', successRate:'99.8%'},
     metrics:{tps:1240, latency:'380ms', inTotal:8642013, outTotal:8641989, watermark:'2026-09-12 22:28:36 (延迟4s)'},
     sql:"-- CDC实时捕获支付流水\nINSERT INTO dwd_order_pay_rt\nSELECT pay_id, order_id, user_id, pay_amount,\n       pay_status, pay_channel,\n       TO_DATE(pay_time) AS dt\nFROM kafka_order_pay\n/*+ OPTIONS('scan.startup.mode'='latest-offset') */\nWHERE pay_amount IS NOT NULL;",
     owner:'刘工', parallelism:4, uptime:'12天3小时', createdAt:'2026-08-30 10:00'},
    {id:'SJ002', name:'设备心跳分钟聚合', type:'Flink SQL', source:'Kafka: topic_iot_heartbeat', sink:'Doris: dws_iot_heartbeat_1m', status:'running',
     checkpoint:{interval:'30s', mode:'Exactly-Once', backend:'RocksDB', lastOk:'2026-09-12 22:29:02', successRate:'100%'},
     metrics:{tps:5300, latency:'120ms', inTotal:43120000, outTotal:986200, watermark:'2026-09-12 22:28:58 (延迟2s)'},
     sql:"-- 滚动窗口：1分钟设备心跳聚合\nINSERT INTO dws_iot_heartbeat_1m\nSELECT device_id,\n       TUMBLE_ROWTIME(proc_time, INTERVAL '1' MINUTE) AS win_start,\n       COUNT(1) AS beat_cnt,\n       AVG(cpu_usage) AS cpu_avg\nFROM kafka_iot_heartbeat\nGROUP BY device_id, TUMBLE(proc_time, INTERVAL '1' MINUTE);",
     owner:'刘工', parallelism:8, uptime:'7天11小时', createdAt:'2026-09-04 14:20'},
    {id:'SJ003', name:'订单宽表实时预览(调试)', type:'Flink SQL', source:'Kafka: topic_order_pay', sink:'打印控制台', status:'stopped',
     checkpoint:{interval:'-', mode:'-', backend:'HashMap', lastOk:'-', successRate:'-'},
     metrics:{tps:0, latency:'-', inTotal:1204, outTotal:1204, watermark:'-'},
     sql:"SELECT pay_id, pay_amount, pay_channel FROM kafka_order_pay;\n-- 实时数据预览：调试SQL逻辑",
     owner:'张工', parallelism:1, uptime:'-', createdAt:'2026-09-10 16:00'},
    {id:'SJ004', name:'库存变更CDC同步', type:'CDC采集', source:'MySQL Binlog: biz_test.inventory', sink:'Kafka: topic_inventory_cdc', status:'paused',
     checkpoint:{interval:'60s', mode:'Exactly-Once', backend:'RocksDB', lastOk:'2026-09-12 14:02:11', successRate:'99.2%'},
     metrics:{tps:0, latency:'-', inTotal:5230110, outTotal:5230110, watermark:'-'},
     sql:"CDC采集任务：Binlog → Kafka（暂停中，等待联调窗口）",
     owner:'刘工', parallelism:2, uptime:'-', createdAt:'2026-09-06 09:30'}
  ],
  windows: [
    {name:'滚动窗口 TUMBLE', desc:'固定长度切分，窗口不重叠', eg:'每1分钟聚合一次心跳'},
    {name:'滑动窗口 HOP', desc:'窗口重叠，按步长滑动', eg:'近5分钟每分钟滑动计算GMV'},
    {name:'会话窗口 SESSION', desc:'按活动间隔动态切分', eg:'用户会话行为分析'}
  ],
  timeSemantics: [
    {name:'事件时间 Event Time', desc:'数据自带时间，配合Watermark处理乱序', use:'业务口径统计（推荐）'},
    {name:'处理时间 Processing Time', desc:'算子处理时的机器时间', use:'低延迟不要求准确的场景'},
    {name:'摄入时间 Ingestion Time', desc:'进入Flink的时间', use:'折中方案'}
  ],

  /* ===== M07 质量管理 ===== */
  qcDims: [
    {code:'COMPLETENESS', name:'完整性', icon:'◧', color:'#1668dc', desc:'字段空值、记录数符合预期'},
    {code:'ACCURACY', name:'准确性', icon:'◈', color:'#7c3aed', desc:'范围校验、业务规则、与源一致'},
    {code:'CONSISTENCY', name:'一致性', icon:'⇋', color:'#0891b2', desc:'跨表/跨系统数据比对一致'},
    {code:'TIMELINESS', name:'及时性', icon:'⏱', color:'#d97706', desc:'数据按时产出、SLA达标'},
    {code:'UNIQUENESS', name:'唯一性', icon:'①', color:'#c2410c', desc:'主键唯一、无重复数据'},
    {code:'VALIDITY', name:'有效性', icon:'✓', color:'#16a34a', desc:'格式、枚举、正则、范围合法'}
  ],
  qcRules: [
    /* 预制规则（系统内置，可停用不可删除） */
    {id:'QC-P-001', name:'身份证号码校验（GB 11643-1999）', table:'ods_gdb_biz_user_info', field:'id_card', dim:'VALIDITY', type:'正则校验', threshold:'18位且末位校验码合法（GB 11643-1999）', level:'强规则', status:'enabled', owner:'系统预制', lastResult:'pass', linkTask:'-', builtin:true, pattern:'^\\d{17}[\\dXx]$'},
    {id:'QC-P-002', name:'手机号校验', table:'ods_gdb_biz_user_info', field:'phone', dim:'VALIDITY', type:'正则校验', threshold:'11位且1[3-9]号段（工信部规范）', level:'强规则', status:'enabled', owner:'系统预制', lastResult:'pass', linkTask:'-', builtin:true, pattern:'^1[3-9]\\d{9}$'},
    {id:'QC-P-003', name:'统一社会信用代码校验（GB 32100-2015）', table:'ods_gdb_biz_trade_order', field:'invoice_uscc', dim:'VALIDITY', type:'正则校验', threshold:'18位且校验位合法（GB 32100-2015）', level:'强规则', status:'enabled', owner:'系统预制', lastResult:'pass', linkTask:'-', builtin:true, pattern:'^[0-9A-HJ-NPQRTUWXY]{2}\\d{6}[0-9A-HJ-NPQRTUWXY]{10}$'},
    {id:'QC-R-001', name:'用户表主键唯一性', table:'ods_gdb_biz_user_info', field:'user_id', dim:'UNIQUENESS', type:'唯一性检查', threshold:'=0 重复', level:'强规则', status:'enabled', owner:'王工', lastResult:'pass', linkTask:'QT001'},
    {id:'QC-R-012', name:'支付金额范围检查', table:'dwd_order_pay_detail', field:'pay_amount', dim:'ACCURACY', type:'范围检查', threshold:'0 ≤ 值 ≤ 500000', level:'强规则', status:'enabled', owner:'李工', lastResult:'fail', linkTask:'QT002'},
    {id:'QC-R-013', name:'手机号非空检查', table:'ods_gdb_biz_user_info', field:'phone', dim:'COMPLETENESS', type:'空值检查', threshold:'空值率 ≤ 1%', level:'弱规则', status:'enabled', owner:'王工', lastResult:'pass', linkTask:'QT001'},
    {id:'QC-R-021', name:'性别枚举合法', table:'ods_gdb_biz_user_info', field:'gender', dim:'VALIDITY', type:'枚举检查', threshold:'值域 ∈ {M,F}', level:'强规则', status:'enabled', owner:'王工', lastResult:'pass', linkTask:'QT001'},
    {id:'QC-R-030', name:'订单-支付跨表金额一致', table:'dwd_order_pay_detail', field:'pay_amount', dim:'CONSISTENCY', type:'跨表一致性', threshold:'与ods_gdb_biz_pay_record SUM差 ≤ 0.01', level:'强规则', status:'enabled', owner:'李工', lastResult:'pass', linkTask:'QT002'},
    {id:'QC-R-031', name:'汇总表及时产出', table:'dws_pay_summary_daily', field:'-', dim:'TIMELINESS', type:'SLA检查', threshold:'每日04:00前产出', level:'强规则', status:'enabled', owner:'李工', lastResult:'pass', linkTask:'QT003'},
    {id:'QC-R-032', name:'订单表行数波动', table:'ods_gdb_biz_trade_order', field:'-', dim:'COMPLETENESS', type:'行数波动', threshold:'日环比波动 ≤ ±30%', level:'弱规则', status:'disabled', owner:'张工', lastResult:'pass', linkTask:'-'}
  ],
  qcTasks: [
    {id:'QT001', name:'ODS层日检任务', tables:3, rules:3, cron:'0 40 2 * * ?', linkEtl:'是（etl_dwd_order_pay_clean前置联动）', status:'enabled', lastRun:'2026-09-12 02:40', lastResult:'success'},
    {id:'QT002', name:'DWD支付明细质量检查', tables:1, rules:2, cron:'0 20 3 * * ?', linkEtl:'是（etl_dws_pay_summary前置联动）', status:'enabled', lastRun:'2026-09-12 03:20', lastResult:'fail'},
    {id:'QT003', name:'DWS/ADS及时性巡检', tables:2, rules:1, cron:'0 0 4 * * ?', linkEtl:'否', status:'enabled', lastRun:'2026-09-12 04:00', lastResult:'success'}
  ],
  qcExceptions: [
    {id:'QE20260912-001', qcId:'QC20260912-002', ruleId:'QC-R-012', ruleName:'支付金额范围检查', table:'dwd_order_pay_detail', field:'pay_amount', dim:'准确性', cnt:12, dt:'2026-09-11', status:'pending', sample:[
      {pay_id:20260911001258, pay_amount:-320.50, desc:'金额为负'},
      {pay_id:20260911002345, pay_amount:-88.00, desc:'金额为负'},
      {pay_id:20260911003671, pay_amount:890000.00, desc:'超出上限50万'}]},
    {id:'QE20260912-002', qcId:'QC20260912-001', ruleId:'QC-R-013', ruleName:'手机号非空检查', table:'ods_gdb_biz_user_info', field:'phone', dim:'完整性', cnt:86, dt:'2026-09-11', status:'fixed', sample:[
      {user_id:100238, phone:null, desc:'phone为空'},
      {user_id:100571, phone:'', desc:'phone为空串'}]},
    {id:'QE20260911-001', qcId:'QC20260911-002', ruleId:'QC-R-012', ruleName:'支付金额范围检查', table:'dwd_order_pay_detail', field:'pay_amount', dim:'准确性', cnt:4, dt:'2026-09-10', status:'ignored', sample:[
      {pay_id:20260910001211, pay_amount:0.00, desc:'0元支付测试单'}]}
  ],
  qcScoreTrend: {labels:['09-05','09-06','09-07','09-08','09-09','09-10','09-11','09-12'], ods:[97,97,96,98,97,97,96,97], dwd:[95,94,93,95,96,92,90,93], dws:[99,99,100,99,99,100,99,100], ads:[100,100,99,100,100,100,100,100]},
  qcDimScore: [
    {name:'完整性', score:96}, {name:'准确性', score:89}, {name:'一致性', score:100},
    {name:'及时性', score:100}, {name:'唯一性', score:98}, {name:'有效性', score:99}
  ],
  qcReports: [
    {id:'QR-20260912-D', name:'数据质量日报 2026-09-12', type:'日报', period:'2026-09-12', score:95, problems:3, fixed:1, status:'published'},
    {id:'QR-20260911-D', name:'数据质量日报 2026-09-11', type:'日报', period:'2026-09-11', score:93, problems:2, fixed:2, status:'published'},
    {id:'QR-20260907-W', name:'数据质量周报 2026-W37', type:'周报', period:'09-01 ~ 09-07', score:96, problems:8, fixed:7, status:'published'},
    {id:'QR-20260831-M', name:'数据质量月报 2026-08', type:'月报', period:'2026-08', score:97, problems:21, fixed:20, status:'published'}
  ],
  qcAlarms: [
    {id:'QA01', name:'强规则失败即时告警', channel:'邮件+短信', scope:'所有强规则失败', threshold:'规则失败即告警', receivers:'王工/李工/值班', status:'enabled'},
    {id:'QA02', name:'弱规则失败汇总告警', channel:'邮件', scope:'弱规则', threshold:'失败数 ≥ 3', receivers:'数据组', status:'enabled'},
    {id:'QA03', name:'评分跌破阈值告警', channel:'邮件+飞书', scope:'全库评分', threshold:'评分 < 90', receivers:'王工/分管领导', status:'enabled'}
  ],
  qcKeepDays: 30,
  /* 质量异常保留策略：异常记录保留30天，到期自动清理 */
  qcRetention: {days: 30, autoClean: true},

  /* ===== 开放接口（本系统产出/运行相关数据的三类 API：流数据/数据质量/元数据） =====
   * 鉴权：X-API-Key 请求头；Key 线下分发；仅绑定 API 范围内的接口可调用 */
  openApis: [
    {id:'OA001', name:'流任务列表查询', path:'/open/api/v1/stream/jobs', method:'GET', category:'流数据', status:'enabled', calls:1284,
     desc:'查询流数据处理任务的运行状态与实时指标（吞吐/延迟/水位线）',
     params:[{name:'status', required:false, desc:'运行状态筛选：running/paused/stopped'}, {name:'keyword', required:false, desc:'任务名/ID 模糊匹配'}],
     respExample:'{"code":0,"data":[{"jobId":"SJ001","name":"实时支付监控","status":"running","throughput":"12,480 条/秒","delayMs":380}]}'},
    {id:'OA002', name:'流窗口聚合指标查询', path:'/open/api/v1/stream/metrics', method:'GET', category:'流数据', status:'enabled', calls:862,
     desc:'按窗口查询流任务聚合指标（窗口类型/键值/聚合结果），支持 CEP 命中统计',
     params:[{name:'jobId', required:true, desc:'流任务ID'}, {name:'window', required:false, desc:'窗口类型：tumble/hop/session'}, {name:'from/to', required:false, desc:'时间范围'}],
     respExample:'{"code":0,"data":[{"window":"2026-09-12 10:00~10:05","key":"ALIPAY","agg":{"pay_amount_sum":528210.55,"pay_cnt":4102}}]}'},
    {id:'OA003', name:'质量报告查询', path:'/open/api/v1/quality/reports', method:'GET', category:'数据质量', status:'enabled', calls:517,
     desc:'查询质量报告（总体/专项/细项）列表与评分详情，供第三方系统调阅',
     params:[{name:'level', required:false, desc:'报告级别：overall/special/detail，缺省全部'}, {name:'wfId', required:false, desc:'专项报告按工作流ID过滤'}, {name:'table', required:false, desc:'细项报告按表名过滤'}],
     respExample:'{"code":0,"data":[{"id":"QR-20260912-D","level":"overall","score":95,"problems":3,"fixed":1}]}'},
    {id:'OA004', name:'质量异常记录查询', path:'/open/api/v1/quality/exceptions', method:'GET', category:'数据质量', status:'enabled', calls:393,
     desc:'查询质量检测异常记录（表/字段/规则/异常行数/状态），支持按时间范围拉取',
     params:[{name:'status', required:false, desc:'pending/fixed/ignored'}, {name:'table', required:false, desc:'表名精确匹配'}, {name:'from/to', required:false, desc:'异常日期范围'}],
     respExample:'{"code":0,"data":[{"id":"QE20260912-001","table":"dwd_order_pay_detail","field":"pay_amount","cnt":12,"status":"pending"}]}'},
    {id:'OA005', name:'元数据表目录查询', path:'/open/api/v1/meta/tables', method:'GET', category:'元数据', status:'enabled', calls:2076,
     desc:'查询资产元数据目录（表名/分层/业务域/密级/行数/负责人），支持按密级鉴权过滤',
     params:[{name:'layer', required:false, desc:'数仓分层：ODS/DWD/DWS/ADS/DIM/TMP'}, {name:'domain', required:false, desc:'业务域'}, {name:'keyword', required:false, desc:'表名/描述模糊匹配'}],
     respExample:'{"code":0,"data":[{"id":"T1","name":"ods_gdb_biz_user_info","layer":"ODS","domain":"公共","security":"机密","rows":1250000}]}'}
  ],
  apiKeys: [
    {id:'AK001', name:'运营分析平台', key:'dk_live_9f3a2c7e81b4d6f0a5c8', apis:['OA003','OA004','OA005'], status:'enabled', owner:'李工', createdAt:'2026-08-30 10:20', lastCalled:'2026-09-12 09:42', calls:2140},
    {id:'AK002', name:'实时大屏系统', key:'dk_live_5b8d1e4f7a2c9306e1b9', apis:['OA001','OA002'], status:'enabled', owner:'王工', createdAt:'2026-09-02 14:05', lastCalled:'2026-09-12 10:01', calls:1186}
  ],
  openLogs: [
    {id:'OL0001', ts:'2026-09-12 10:01:08', keyId:'AK002', keyName:'实时大屏系统', apiId:'OA001', apiPath:'/open/api/v1/stream/jobs', params:'status=running', httpStatus:200, costMs:46, result:'success', msg:'返回 3 条'},
    {id:'OL0002', ts:'2026-09-12 09:42:31', keyId:'AK001', keyName:'运营分析平台', apiId:'OA003', apiPath:'/open/api/v1/quality/reports', params:'level=overall', httpStatus:200, costMs:88, result:'success', msg:'返回 4 条'},
    {id:'OL0003', ts:'2026-09-12 09:40:12', keyId:'AK001', keyName:'运营分析平台', apiId:'OA001', apiPath:'/open/api/v1/stream/jobs', params:'status=running', httpStatus:403, costMs:3, result:'denied', msg:'Key 未绑定该 API（OA001 不在授权范围）'},
    {id:'OL0004', ts:'2026-09-12 08:15:44', keyId:'AK002', keyName:'实时大屏系统', apiId:'OA002', apiPath:'/open/api/v1/stream/metrics', params:'jobId=SJ001&window=tumble', httpStatus:200, costMs:132, result:'success', msg:'返回 12 条'},
    {id:'OL0005', ts:'2026-09-11 22:03:19', keyId:'AK001', keyName:'运营分析平台', apiId:'OA005', apiPath:'/open/api/v1/meta/tables', params:'layer=ODS&keyword=gdb', httpStatus:200, costMs:64, result:'success', msg:'返回 4 条'}
  ],

  /* ===== M09 元数据 ===== */
  bizDomains: [
    {name:'交易域', color:'#1668dc', tables:48, models:12, indicators:16, desc:'订单、支付、退款等交易过程数据'},
    {name:'经营域', color:'#16a34a', tables:36, models:9, indicators:22, desc:'KPI、预算、经营分析'},
    {name:'商品域', color:'#d97706', tables:22, models:6, indicators:8, desc:'商品、库存、类目'},
    {name:'财务域', color:'#7c3aed', tables:28, models:7, indicators:11, desc:'凭证、应收应付、总账'},
    {name:'公共', color:'#0891b2', tables:18, models:5, indicators:4, desc:'用户、机构、字典等公共维度'}
  ],
  metaTables: [
    {id:'T1', name:'ods_gdb_biz_user_info', layer:'ODS', domain:'公共', rows:1250000, size:'320MB', owner:'王工', tags:['核心'], yesterdayOk:true, security:'机密', desc:'万里生产用户信息原样同步', sample:[{user_id:100001,user_name:'张伟',gender:'M',phone:'138****1234',create_time:'2026-01-03 10:21:00'},{user_id:100002,user_name:'王芳',gender:'F',phone:'139****5678',create_time:'2026-01-03 11:45:00'},{user_id:100003,user_name:'李娜',gender:'F',phone:'137****9012',create_time:'2026-01-04 08:30:00'}]},
    {id:'T2', name:'ods_gdb_biz_trade_order', layer:'ODS', domain:'交易域', rows:4100000, size:'1.2GB', owner:'王工', tags:['核心'], yesterdayOk:true, security:'内部', desc:'万里生产交易订单原样同步', sample:[{order_id:90001,user_id:100001,amount:299.00,status:'1',create_time:'2026-09-11 09:00:12'},{order_id:90002,user_id:100002,amount:1299.00,status:'1',create_time:'2026-09-11 09:12:40'}]},
    {id:'T3', name:'dwd_order_pay_detail', layer:'DWD', domain:'交易域', rows:3980000, size:'860MB', owner:'李工', tags:['核心','已映射'], yesterdayOk:true, security:'机密', desc:'清洗后的支付明细事实表', sample:[{pay_id:20260911000001,order_id:90001,user_id:100001,pay_amount:299.00,pay_status:1,channel:'ALIPAY',dt:'2026-09-11'},{pay_id:20260911000002,order_id:90002,user_id:100002,pay_amount:1299.00,pay_status:1,channel:'WECHAT',dt:'2026-09-11'}]},
    {id:'T4', name:'dws_pay_summary_daily', layer:'DWS', domain:'交易域', rows:1860, size:'2MB', owner:'李工', tags:['核心'], yesterdayOk:true, security:'内部', desc:'支付主题日汇总', sample:[{stat_date:'2026-09-11',channel:'ALIPAY',pay_user_cnt:3210,pay_order_cnt:4102,pay_amount_sum:528210.55},{stat_date:'2026-09-11',channel:'WECHAT',pay_user_cnt:2890,pay_order_cnt:3640,pay_amount_sum:451870.20}]},
    {id:'T5', name:'ads_kpi_report', layer:'ADS', domain:'经营域', rows:365, size:'1MB', owner:'赵工', tags:['报表'], yesterdayOk:true, security:'公开', desc:'经营KPI报表宽表', sample:[{stat_date:'2026-09-11',gmv:980080.75,pay_user_cnt:5660,pay_amount_7d:6520000.00}]},
    {id:'T6', name:'dim_user', layer:'DIM', domain:'公共', rows:1250000, size:'210MB', owner:'王工', tags:['核心','已映射'], yesterdayOk:true, security:'机密', desc:'用户公共维度表', sample:[{user_id:100001,user_name:'张伟',org_name:'大发局',user_level:'02'}]},
    {id:'T7', name:'ods_oracle_gl_voucher', layer:'ODS', domain:'财务域', rows:560000, size:'420MB', owner:'赵工', tags:['涉密'], yesterdayOk:true, security:'绝密', desc:'ERP总账凭证原样同步', sample:[{voucher_id:'V20260911001',subject:'1001库存现金',debit:12000.00,credit:0,dt:'2026-09-11'}]},
    {id:'T8', name:'ods_mysql_product_info', layer:'ODS', domain:'商品域', rows:78000, size:'95MB', owner:'张工', tags:['差异待核'], yesterdayOk:false, security:'内部', desc:'MySQL商品信息同步（存在2000行差异）', sample:[{product_id:1,product_name:'数据治理服务包年',price:98000.00,dt:'2026-09-11'}]}
  ],
  tableLineage: [
    {from:'ods_gdb_biz_trade_order', to:'dwd_order_pay_detail', task:'etl_dwd_order_pay_clean (ETL001)', wf:'WF-订单主题日增'},
    {from:'ods_gdb_biz_user_info', to:'dim_user', task:'etl_dim_user_sync (ETL005)', wf:'WF-维度日更'},
    {from:'ods_gdb_biz_pay_record', to:'dwd_order_pay_detail', task:'etl_dwd_order_pay_clean (ETL001)', wf:'WF-订单主题日增'},
    {from:'dim_user', to:'dwd_order_pay_detail', task:'etl_dwd_order_pay_clean (ETL001)', wf:'WF-订单主题日增'},
    {from:'dwd_order_pay_detail', to:'dws_pay_summary_daily', task:'etl_dws_pay_summary (ETL002)', wf:'WF-订单主题日增'},
    {from:'dws_pay_summary_daily', to:'ads_kpi_report', task:'etl_ads_kpi (ETL003)', wf:'WF-经营KPI'},
    {from:'ods_oracle_gl_voucher', to:'dwd_gl_voucher_detail', task:'etl_dwd_gl_voucher (ETL004)', wf:'未入工作流'},
    {from:'ods_mysql_product_info', to:'dim_product', task:'etl_dim_product_sync (ETL006)', wf:'未入工作流'}
  ],
  fieldLineage: {
    'dwd_order_pay_detail.pay_amount': [
      {from:'ods_gdb_biz_trade_order.amount', transform:'amount - discount（ETL表达式算子）'},
      {from:'ods_gdb_biz_pay_record.pay_amount', transform:'直接映射'}
    ],
    'dws_pay_summary_daily.pay_amount_sum': [
      {from:'dwd_order_pay_detail.pay_amount', transform:'SUM(pay_amount) GROUP BY stat_date, channel'}
    ],
    'ads_kpi_report.pay_amount_7d': [
      {from:'dws_pay_summary_daily.pay_amount_sum', transform:'近7天滚动求和'}
    ]
  },
  impactExample: {
    table:'dwd_order_pay_detail',
    downTables:[{name:'dws_pay_summary_daily',task:'ETL002'},{name:'ads_kpi_report',task:'ETL003'}],
    downTasks:[{name:'etl_dws_pay_summary',wf:'WF-订单主题日增',type:'SQL任务'},{name:'etl_ads_kpi',wf:'WF-经营KPI',type:'SQL任务'}],
    downIndicators:[{name:'近7天支付金额',code:'METRIC_002'},{name:'客单价',code:'METRIC_005'}],
    reports:['经营日报','支付渠道分析']
  },
  metaTags: [
    {id:'TG01', name:'核心', cat:'重要性', color:'#e5484d', cnt:6, desc:'影响生产决策的高优先级表', tables:['T1','T2','T3','T4','T6']},
    {id:'TG02', name:'报表', cat:'用途', color:'#1668dc', cnt:2, desc:'直接服务报表的表', tables:['T5']},
    {id:'TG03', name:'已映射', cat:'标准', color:'#16a34a', cnt:2, desc:'已完成数据标准映射', tables:['T3','T6']},
    {id:'TG04', name:'涉密', cat:'安全', color:'#7c3aed', cnt:1, desc:'涉密数据，访问受限', tables:['T7']},
    {id:'TG05', name:'差异待核', cat:'质量', color:'#d97706', cnt:1, desc:'同步存在数据量差异', tables:['T8']}
  ],

  /* ===== M10 数据标准 ===== */
  stdElements: [
    {id:'DE-001', cn:'用户ID', en:'user_id', type:'BIGINT', len:'-', format:'非空正整数', domain:'公共', desc:'全系统统一用户唯一标识', status:'published', v:2, owner:'王工', updatedAt:'2026-09-06'},
    {id:'DE-002', cn:'手机号', en:'phone', type:'VARCHAR', len:20, format:'11位数字 1[3-9]开头', domain:'公共', desc:'用户联系手机号', status:'published', v:1, owner:'王工', updatedAt:'2026-08-30'},
    {id:'DE-003', cn:'支付金额', en:'pay_amount', type:'DECIMAL', len:'(18,2)', format:'≥0，单位元', domain:'交易域', desc:'订单实际支付金额', status:'published', v:3, owner:'李工', updatedAt:'2026-09-11'},
    {id:'DE-004', cn:'支付渠道', en:'pay_channel', type:'VARCHAR', len:20, format:'代码标准 C-005', domain:'交易域', desc:'支付渠道编码', status:'review', v:2, owner:'李工', updatedAt:'2026-09-12'},
    {id:'DE-005', cn:'统计日期', en:'stat_date', type:'DATE', len:'-', format:'yyyy-MM-dd', domain:'公共', desc:'数据统计归属日期', status:'published', v:1, owner:'赵工', updatedAt:'2026-08-25'}
  ],
  stdCodes: [
    {id:'C-003', name:'用户等级', values:[{c:'01',n:'普通用户'},{c:'02',n:'VIP用户'},{c:'03',n:'SVIP用户'}], status:'published', used:6},
    {id:'C-005', name:'支付渠道', values:[{c:'ALIPAY',n:'支付宝'},{c:'WECHAT',n:'微信支付'},{c:'UNIONPAY',n:'银联'},{c:'BANK',n:'银行卡'}], status:'published', used:4},
    {id:'C-006', name:'订单状态', values:[{c:'01',n:'待支付'},{c:'02',n:'已支付'},{c:'03',n:'已发货'},{c:'04',n:'已完成'},{c:'05',n:'已取消'}], status:'published', used:8},
    {id:'C-007', name:'币种', values:[{c:'CNY',n:'人民币'},{c:'USD',n:'美元'}], status:'draft', used:0}
  ],
  namingRules: [
    {id:'NR-01', scope:'表命名-Ods', pattern:'^ods_[源库名]_[源表名]$', eg:'ods_gdb_biz_user_info', desc:'ODS层表命名规范', status:'published'},
    {id:'NR-02', scope:'表命名-Dwd', pattern:'^dwd_[业务域]_[业务过程]$', eg:'dwd_order_pay_detail', desc:'DWD层表命名规范', status:'published'},
    {id:'NR-03', scope:'表命名-Dws', pattern:'^dws_[主题]_[粒度]$', eg:'dws_pay_summary_daily', desc:'DWS层表命名规范', status:'published'},
    {id:'NR-04', scope:'表命名-Ads', pattern:'^ads_[应用]_[场景]$', eg:'ads_kpi_report', desc:'ADS层表命名规范', status:'published'},
    {id:'NR-05', scope:'字段命名', pattern:'^[a-z][a-z0-9_]*$（snake_case，禁止拼音）', eg:'user_id / pay_amount', desc:'字段snake_case规范', status:'published'},
    {id:'NR-06', scope:'任务命名', pattern:'^(etl|sync)_[目标表]_[动作]$', eg:'etl_dws_pay_summary', desc:'任务命名规范', status:'published'}
  ],
  stdMappings: [
    {id:'SM001', table:'dwd_order_pay_detail', field:'pay_amount', stdId:'DE-003', stdName:'支付金额', result:'pass', diff:'类型/精度一致', checkedAt:'2026-09-11 10:05'},
    {id:'SM002', table:'dwd_order_pay_detail', field:'pay_channel', stdId:'DE-004', stdName:'支付渠道', result:'fail', diff:'字段注释缺渠道枚举说明（对照C-005）', checkedAt:'2026-09-11 10:05'},
    {id:'SM003', table:'dim_user', field:'user_level', stdId:'C-003', stdName:'用户等级', result:'pass', diff:'枚举一致', checkedAt:'2026-09-06 16:40'},
    {id:'SM004', table:'ods_gdb_biz_user_info', field:'gender', stdId:'DE-006', stdName:'性别', result:'pass', diff:'值域 M/F 一致', checkedAt:'2026-09-10 15:20'},
    {id:'SM005', table:'dim_user', field:'org_name', stdId:'DE-007', stdName:'机构名称', result:'fail', diff:'长度200超标准100，建议截断或扩标', checkedAt:'2026-09-06 16:40'}
  ],
  stdApprovals: [
    {id:'SA20260912-01', type:'数据元标准', target:'DE-004 支付渠道（v2）', proposer:'李工', submitAt:'2026-09-12 10:20', flow:['起草','评审','发布'], current:1, status:'review', opinion:''},
    {id:'SA20260910-03', type:'代码标准', target:'C-003 用户等级（v2，增SVIP）', proposer:'王工', submitAt:'2026-09-10 09:00', flow:['起草','评审','发布'], current:3, status:'published', opinion:'评审通过，已发布执行'}
  ],

  /* ===== M10 指标 ===== */
  indicators: [
    {id:'METRIC_001', name:'支付金额', en:'pay_amount', type:'原子', bizDef:'成功支付订单的金额总和（不含退款）', techDef:'SUM(pay_amount) WHERE pay_status=1',
     srcTable:'dwd_order_pay_detail', srcField:'pay_amount', outTable:'-', outTask:'-', period:'-', dims:'-', owner:'李工', domain:'交易域', status:'published', v:2,
     trend:[128,135,142,138,150,146,158,152], unit:'万元',
     versions:[{v:2,date:'2026-09-08',note:'口径明确不含退款',author:'李工'},{v:1,date:'2026-08-25',note:'初版',author:'李工'}]},
    {id:'METRIC_002', name:'近7天支付金额', en:'pay_amount_7d', type:'派生', bizDef:'最近7个自然日成功支付订单总金额（不含退款）',
     techDef:'SUM(pay_amount) WHERE pay_status=1 AND dt BETWEEN date_sub(current_date,7) AND date_sub(current_date,1)',
     srcTable:'dwd_order_pay_detail', srcField:'pay_amount', outTable:'ads_kpi_report', outTask:'ETL003 etl_ads_kpi', period:'近7天', dims:'日期', owner:'赵工', domain:'经营域', status:'published', v:2,
     trend:[880,920,905,960,988,1010,1052,1076], unit:'万元', baseMetric:'METRIC_001',
     versions:[{v:2,date:'2026-09-11',note:'限定剔除退款单（审批中变更撤销）',author:'赵工'},{v:1,date:'2026-08-26',note:'初版',author:'赵工'}]},
    {id:'METRIC_003', name:'支付用户数', en:'pay_user_cnt', type:'原子', bizDef:'当日成功支付的去重用户数', techDef:'COUNT(DISTINCT user_id) WHERE pay_status=1',
     srcTable:'dwd_order_pay_detail', srcField:'user_id', outTable:'dws_pay_summary_daily', outTask:'ETL002', period:'日', dims:'日期/渠道', owner:'李工', domain:'交易域', status:'published', v:1,
     trend:[5200,5350,5410,5580,5620,5660,5780,5902], unit:'人',
     versions:[{v:1,date:'2026-08-25',note:'初版',author:'李工'}]},
    {id:'METRIC_004', name:'本月下单量', en:'order_cnt_month', type:'派生', bizDef:'本月累计成功下单笔数', techDef:'COUNT(1) WHERE create_time >= month_start AND status != 05',
     srcTable:'dwd_order_pay_detail', srcField:'order_id', outTable:'ads_kpi_report', outTask:'ETL003', period:'本月', dims:'日期', owner:'赵工', domain:'交易域', status:'published', v:1,
     trend:[42000,43500,44100,45800,46900,47500,48200,49100], unit:'笔', baseMetric:'-',
     versions:[{v:1,date:'2026-08-26',note:'初版',author:'赵工'}]},
    {id:'METRIC_005', name:'客单价', en:'avg_order_value', type:'计算', bizDef:'支付金额 / 支付订单数，平均每单支付金额', techDef:'pay_amount_sum / pay_order_cnt',
     srcTable:'dws_pay_summary_daily', srcField:'pay_amount_sum', outTable:'-', outTask:'-', period:'日', dims:'-', owner:'李工', domain:'交易域', status:'published', v:1, formula:'METRIC_001 / 支付订单数',
     trend:[142,145,148,146,150,152,153,155], unit:'元',
     versions:[{v:1,date:'2026-08-27',note:'初版',author:'李工'}]},
    {id:'METRIC_006', name:'支付转化率', en:'pay_conv_rate', type:'计算', bizDef:'支付用户数 / 访问用户数', techDef:'pay_user_cnt / visit_user_cnt',
     srcTable:'dws_pay_summary_daily', srcField:'pay_user_cnt', outTable:'-', outTask:'-', period:'日', dims:'-', owner:'李工', domain:'交易域', status:'published', v:2, formula:'支付用户数 / 访问用户数 × 100%',
     trend:[0.62,0.63,0.61,0.64,0.65,0.64,0.66,0.67], unit:'%', changeNote:'访问口径从PV调整为UV',
     versions:[{v:2,date:'2026-09-11',note:'访问口径PV→UV',author:'李工'},{v:1,date:'2026-08-28',note:'初版',author:'李工'}]}
  ],
  indConsistency: [
    {metric:'支付金额', places:['ads_kpi_report.gmv口径','支付渠道分析报表','经营日报'], result:'fail', detail:'经营日报按"含退款"口径计算，与标准（不含退款）不一致，差异约2.1%'},
    {metric:'支付用户数', places:['dws_pay_summary_daily','用户活跃分析'], result:'pass', detail:'口径一致'},
    {metric:'本月下单量', places:['ads_kpi_report','运营周报'], result:'pass', detail:'口径一致'}
  ],

  /* ===== M12 参数 ===== */
  globalParams: [
    {id:'GP01', name:'env', value:'prod', type:'文本', encrypt:false, desc:'环境标识', env:'prod', updatedAt:'2026-08-20'},
    {id:'GP02', name:'doris_host', value:'192.168.30.20:9030', type:'文本', encrypt:false, desc:'Doris FE地址', env:'prod', updatedAt:'2026-08-20'},
    {id:'GP03', name:'dw_user', value:'dw_admin', type:'文本', encrypt:false, desc:'数仓账号', env:'prod', updatedAt:'2026-08-20'},
    {id:'GP04', name:'dw_pwd', value:'******', type:'文本', encrypt:true, desc:'数仓密码（加密存储，界面脱敏）', env:'prod', updatedAt:'2026-08-20'},
    {id:'GP05', name:'alarm_mail', value:'duty@datara.cn', type:'文本', encrypt:false, desc:'告警邮箱', env:'prod', updatedAt:'2026-08-25'},
    {id:'GP06', name:'max_retry', value:'3', type:'数值', encrypt:false, desc:'全局默认重试次数', env:'prod', updatedAt:'2026-09-01'}
  ],
  builtinParams: [
    {name:'${biz_date}', desc:'业务日期（T-1，默认昨天）', eg:'2026-09-11'},
    {name:'${today}', desc:'今天日期', eg:'2026-09-12'},
    {name:'${date(-1)}', desc:'相对今天-1天', eg:'2026-09-11'},
    {name:'${date(-7)}', desc:'相对今天-7天', eg:'2026-09-05'},
    {name:'${month_start}', desc:'本月1号', eg:'2026-09-01'},
    {name:'${month_end}', desc:'本月最后一天', eg:'2026-09-30'},
    {name:'${last_month_start}', desc:'上月1号', eg:'2026-08-01'},
    {name:'${last_month_end}', desc:'上月最后一天', eg:'2026-08-31'},
    {name:'${year}', desc:'当前年份', eg:'2026'},
    {name:'${hour}', desc:'当前小时', eg:'22'},
    {name:'${timestamp}', desc:'当前时间戳', eg:'1789238400'},
    {name:'${yyyyMMdd_HHmmss}', desc:'自定义格式时间', eg:'20260912_223000'}
  ],
  envGroups: [
    {name:'dev', desc:'开发环境', cnt:6, ds:'万里GreatDB-开发环境库', params:'env=dev / doris_host=…40.21 / dw_user=dev'},
    {name:'staging', desc:'联调环境', cnt:6, ds:'MySQL-业务测试库', params:'env=staging / doris_host=…30.20 / dw_user=olap'},
    {name:'prod', desc:'生产环境', cnt:6, ds:'Doris-分析集群', params:'env=prod / doris_host=…30.20 / dw_user=dw_admin'}
  ],
  refCheckResult: [
    {file:'ETL002 支付主题日汇总SQL', refs:['${biz_date}'], result:'pass', detail:'biz_date为内置时间参数，可用'},
    {file:'ETL003 经营KPI宽表加工', refs:['${biz_date}','${target_table}'], result:'pass', detail:'target_table为工作流WF-经营KPI变量，可用'},
    {file:'ETL004 ERP财务凭证清洗.py', refs:['${dw_pwd}','${src_schema}'], result:'fail', detail:'${src_schema} 未在任何层级定义，请检查拼写或在参数管理中新增'}
  ],
  paramPreview: [
    {name:'env', scope:'全局(prod)', value:'prod'},
    {name:'biz_date', scope:'内置时间', value:'2026-09-11'},
    {name:'target_table', scope:'工作流变量(WF-经营KPI)', value:'ads_kpi_report'},
    {name:'limit', scope:'节点参数(etl_ads_kpi)', value:'1000'},
    {name:'dw_pwd', scope:'全局(prod·加密)', value:'******'}
  ],

  /* ===== M13 DAG ===== */
  workflows: [
    {id:'WF001', name:'订单主题日增', cron:'0 30 2 * * ?', owner:'李工', status:'online', nodes:5, lastRun:'2026-09-12 02:30', lastResult:'failed',
     desc:'ODS订单→DWD明细→DWS汇总→ADS KPI 主链路',
     nodesDetail:[
       {id:'n1', name:'同步订单表', type:'ETL节点', dep:[], outTable:'ods_gdb_biz_trade_order', retry:2, dur:'150s'},
       {id:'n2', name:'清洗支付明细', type:'ETL节点', dep:['n1'], outTable:'dwd_order_pay_detail', retry:2, dur:'95s'},
       {id:'n3', name:'支付日汇总', type:'SQL节点', dep:['n2'], outTable:'dws_pay_summary_daily', retry:3, dur:'40s'},
       {id:'n4', name:'经营KPI加工', type:'SQL节点', dep:['n3'], outTable:'ads_kpi_report', retry:2, dur:'35s'},
       {id:'n5', name:'质量巡检', type:'子工作流', dep:['n4'], outTable:'-', retry:1, dur:'60s'}
     ]},
    {id:'WF002', name:'维度日更', cron:'0 0 2 * * ?', owner:'王工', status:'online', nodes:2, lastRun:'2026-09-12 02:00', lastResult:'success',
     desc:'用户/商品等公共维度表日更',
     nodesDetail:[
       {id:'n1', name:'同步用户维度', type:'ETL节点', dep:[], outTable:'dim_user', retry:2, dur:'80s'},
       {id:'n2', name:'同步商品维度', type:'ETL节点', dep:[], outTable:'dim_product', retry:2, dur:'30s'}
     ]},
    {id:'WF003', name:'经营KPI', cron:'0 0 4 * * ?', owner:'赵工', status:'online', nodes:2, lastRun:'2026-09-12 04:00', lastResult:'success',
     desc:'依赖订单主题产出表 ads_kpi_report 加工经营日报',
     nodesDetail:[
       {id:'n1', name:'等待ads_kpi_report(表依赖)', type:'依赖检查', dep:[], outTable:'ads_kpi_report（表级依赖 WF001·周期T-1）', retry:0, dur:'2s'},
       {id:'n2', name:'生成经营日报', type:'SQL节点', dep:['n1'], outTable:'ads_daily_report', retry:2, dur:'50s'}
     ]},
    {id:'WF004', name:'财务凭证入仓', cron:'0 0 1 * * ?', owner:'赵工', status:'draft', nodes:2, lastRun:'-', lastResult:'-',
     desc:'Oracle ERP凭证数据入仓（草稿，待评审发布）',
     nodesDetail:[
       {id:'n1', name:'同步ERP凭证', type:'ETL节点', dep:[], outTable:'ods_oracle_gl_voucher', retry:2, dur:'55s'},
       {id:'n2', name:'凭证清洗', type:'脚本节点', dep:['n1'], outTable:'dwd_gl_voucher_detail', retry:1, dur:'120s'}
     ]}
  ],
  /* 工作流局部变量：每个工作流定义独立变量，支持默认值/加密值/下拉选择 */
  wfVariables: [
    {id:'WFV001', wf:'wf_order_daily', name:'biz_date', value:'${date(-1)}', type:'日期', encrypted:false, options:[], desc:'业务日期（T-1）'},
    {id:'WFV002', wf:'wf_order_daily', name:'target_table', value:'ads_kpi_report', type:'文本', encrypted:false, options:[], desc:'KPI结果目标表'},
    {id:'WFV003', wf:'wf_order_daily', name:'db_pwd', value:'******', type:'加密', encrypted:true, options:[], desc:'目标库密码（加密存储，界面脱敏）'},
    {id:'WFV004', wf:'wf_order_daily', name:'env', value:'prod', type:'下拉', encrypted:false, options:['prod','staging','dev'], desc:'运行环境（下拉选择，默认 prod）'},
    {id:'WFV005', wf:'wf_order_daily', name:'retry_times', value:'2', type:'数值', encrypted:false, options:[], desc:'失败重试次数'}
  ],
  wfInstances: [
    {id:'R20260912-001', wf:'WF001', wfName:'订单主题日增', bizDate:'2026-09-11', status:'failed', startAt:'2026-09-12 02:30', endAt:'-', dur:'-', execNode:'批量同步执行节点',
     nodes:[
       {id:'n1', name:'同步订单表', status:'success', start:'02:30:05', end:'02:32:35', dur:'150s', retry:0},
       {id:'n2', name:'清洗支付明细', status:'success', start:'02:32:36', end:'02:34:11', dur:'95s', retry:0},
       {id:'n3', name:'支付日汇总', status:'failed', start:'02:34:12', end:'02:34:41', dur:'29s', retry:3, err:"SQL错误 [1105]: errCode = 2, detailMessage = Unknown column 'pay_channel' in 'dwd_order_pay_detail'"},
       {id:'n4', name:'经营KPI加工', status:'waiting', start:'-', end:'-', dur:'-', retry:0},
       {id:'n5', name:'质量巡检', status:'waiting', start:'-', end:'-', dur:'-', retry:0}
     ]},
    {id:'R20260912-002', wf:'WF002', wfName:'维度日更', bizDate:'2026-09-11', status:'success', startAt:'2026-09-12 02:00', endAt:'2026-09-12 02:03', dur:'3m', execNode:'脚本备份节点',
     nodes:[
       {id:'n1', name:'同步用户维度', status:'success', start:'02:00:02', end:'02:01:22', dur:'80s', retry:0},
       {id:'n2', name:'同步商品维度', status:'success', start:'02:00:02', end:'02:00:32', dur:'30s', retry:0}
     ]},
    {id:'R20260912-003', wf:'WF003', wfName:'经营KPI', bizDate:'2026-09-11', status:'success', startAt:'2026-09-12 04:00', endAt:'2026-09-12 04:04', dur:'4m', execNode:'本地节点',
     nodes:[
       {id:'n1', name:'等待ads_kpi_report(表依赖)', status:'success', start:'04:00:00', end:'04:00:02', dur:'2s', retry:0},
       {id:'n2', name:'生成经营日报', status:'success', start:'04:00:03', end:'04:00:53', dur:'50s', retry:0}
     ]},
    {id:'R20260911-001', wf:'WF001', wfName:'订单主题日增', bizDate:'2026-09-10', status:'success', startAt:'2026-09-11 02:30', endAt:'2026-09-11 02:41', dur:'11m', execNode:'批量同步执行节点',
     nodes:[
       {id:'n1', name:'同步订单表', status:'success', start:'02:30:05', end:'02:32:35', dur:'150s', retry:0},
       {id:'n2', name:'清洗支付明细', status:'success', start:'02:32:36', end:'02:34:11', dur:'95s', retry:0},
       {id:'n3', name:'支付日汇总', status:'success', start:'02:34:12', end:'02:34:52', dur:'40s', retry:0},
       {id:'n4', name:'经营KPI加工', status:'success', start:'02:34:53', end:'02:35:28', dur:'35s', retry:0},
       {id:'n5', name:'质量巡检', status:'success', start:'02:35:29', end:'02:36:29', dur:'60s', retry:0}
     ]}
  ],
  tableDeps: [
    {down:{wf:'WF003', task:'生成经营日报'}, up:{wf:'WF001', task:'经营KPI加工'}, table:'ads_kpi_report', period:'T-1', strategy:'等待完成', check:'已校验：分区 dt=2026-09-11 有数据'},
    {down:{wf:'WF001', task:'支付日汇总'}, up:{wf:'WF001', task:'清洗支付明细'}, table:'dwd_order_pay_detail', period:'T', strategy:'等待完成', check:'校验通过'},
    {down:{wf:'WF001', task:'质量巡检'}, up:{wf:'WF001', task:'经营KPI加工'}, table:'ads_kpi_report', period:'T', strategy:'等待完成', check:'校验通过'}
  ],
  dagAlarms: [
    {id:'DA01', name:'工作流失败告警', scope:'所有工作流', event:'节点最终失败', channel:'邮件+短信', receivers:'王工/任务负责人', status:'enabled'},
    {id:'DA02', name:'断点恢复通知', scope:'所有工作流', event:'恢复运行/自动续跑完成', channel:'邮件', receivers:'任务负责人', status:'enabled'},
    {id:'DA03', name:'SLA超时告警', scope:'WF001/WF003', event:'工作流整体超4小时未完成', channel:'邮件+飞书', receivers:'王工/值班', status:'enabled'}
  ],
  slaRules: [
    {id:'SLA01', wf:'WF001 订单主题日增', deadLine:'每日 06:00 前完成', today:'-超时（n3失败阻塞）', status:'failed', history:'近30天达标 28 天'},
    {id:'SLA02', wf:'WF002 维度日更', deadLine:'每日 03:00 前完成', today:'02:03 完成 ✓', status:'success', history:'近30天达标 30 天'},
    {id:'SLA03', wf:'WF003 经营KPI', deadLine:'每日 05:00 前完成', today:'04:04 完成 ✓', status:'success', history:'近30天达标 29 天'}
  ],

  /* ===== M14 脚本 ===== */
  scripts: [
    {id:'SC001', name:'脏数据隔离清理', lang:'Python', status:'published', owner:'李工', updated:'2026-09-10',
     code:"import sys\nimport pandas as pd\n# 参数：${src_table} 源表  ${biz_date} 业务日期\nsrc = sys.argv[1] if len(sys.argv) > 1 else 'dwd_order_pay_detail'\nprint(f'[INFO] 开始清理脏数据: {src} dt=${biz_date}')\ndf = pd.read_parquet(f'/data/ods/{src}/dt=${biz_date}')\nbad = df[df['pay_amount'] < 0]\nprint(f'[INFO] 捕获脏数据 {len(bad)} 行，写入隔离区')\nbad.to_parquet('/data/quarantine/part.parquet')\nprint('[OK] 清理完成')"},
    {id:'SC002', name:'分区预创建', lang:'Shell', status:'published', owner:'王工', updated:'2026-09-05',
     code:"#!/bin/bash\n# 未来7天分区预创建\nTODAY=$(date +%Y-%m-%d)\nfor i in $(seq 1 7); do\n  D=$(date -d \"$TODAY +$i day\" +%Y-%m-%d)\n  echo \"[INFO] ALTER TABLE ods_gdb_biz_trade_order ADD PARTITION dt=$D\"\ndone\necho '[OK] 分区预创建完成'"},
    {id:'SC003', name:'达梦数据抽取校验', lang:'Python', status:'draft', owner:'赵工', updated:'2026-09-11',
     code:"import dmPython\n# 连接达梦DM8校验抽取行数\nconn = dmPython.connect(user='mgmt_read', server='192.168.10.35')\ncur = conn.cursor()\ncur.execute('SELECT COUNT(1) FROM BUDGET_YEAR')\nprint('达梦源表行数:', cur.fetchone())"},
    {id:'SC004', name:'Java报表生成', lang:'Java', status:'disabled', owner:'张工', updated:'2026-09-08',
     code:"// Java 在线编辑编译执行已排后（P0范围外），当前仅保留查看\npublic class ReportGen {\n  public static void main(String[] args) {\n    System.out.println(\"generate daily report\");\n  }\n}"}
  ],
  pyEnvs: [
    {id:'VENV01', name:'py3-data', python:'3.10.4', pkgs:[{n:'pandas',v:'2.1.1'},{n:'numpy',v:'1.26.0'},{n:'pyarrow',v:'14.0.0'}], status:'enabled', used:2},
    {id:'VENV02', name:'py3-dm', python:'3.10.4', pkgs:[{n:'dmPython',v:'2.4'},{n:'pandas',v:'2.1.1'}], status:'enabled', used:1}
  ],
  execLogs: [
    {id:'LOG20260912-001', script:'SC002 分区预创建', mode:'本地执行', status:'success', start:'2026-09-12 01:55', dur:'3s',
     content:"[2026-09-12 01:55:02] [INFO] 开始执行分区预创建...\n[2026-09-12 01:55:02] [INFO] ALTER TABLE ods_gdb_biz_trade_order ADD PARTITION dt=2026-09-13\n[2026-09-12 01:55:03] [INFO] ... dt=2026-09-14 ~ dt=2026-09-19\n[2026-09-12 01:55:04] [OK] 分区预创建完成，退出码 0"},
    {id:'LOG20260912-002', script:'SC001 脏数据隔离清理', mode:'远程执行(SSH: 192.168.30.31)', status:'failed', start:'2026-09-12 03:25', dur:'12s',
     content:"[2026-09-12 03:25:10] [INFO] 开始清理脏数据: dwd_order_pay_detail dt=2026-09-11\n[2026-09-12 03:25:18] [ERROR] FileNotFoundError: /data/ods/dwd_order_pay_detail/dt=2026-09-11 不存在\n[2026-09-12 03:25:20] [WARN] 退出码 1，请检查上游产出分区\n[2026-09-12 03:25:20] 任务失败，已触发告警(邮件+短信)"},
    {id:'LOG20260911-003', script:'SC003 达梦数据抽取校验', mode:'本地执行', status:'success', start:'2026-09-11 14:32', dur:'6s',
     content:"[2026-09-11 14:32:20] [INFO] 连接达梦DM8 192.168.10.35:5236 成功\n[2026-09-11 14:32:24] [INFO] 达梦源表行数: 12500\n[2026-09-11 14:32:26] [OK] 校验通过，退出码 0"}
  ],
  remoteNodes: [
    {id:'RN01', name:'批量同步执行节点', ip:'192.168.30.31', os:'麒麟V10(鲲鹏920)', mode:'SSH', auth:'密钥(datara_key)', status:'online', lastPing:'2026-09-12 22:20', scripts:3},
    {id:'RN02', name:'脚本备份节点', ip:'192.168.30.32', os:'麒麟V10(鲲鹏920)', mode:'SSH', auth:'密码(加密存储)', status:'online', lastPing:'2026-09-12 22:19', scripts:1},
    {id:'RN03', name:'东信云前置机', ip:'10.20.8.15', os:'麒麟V10(x86)', mode:'SSH', auth:'密钥(vpn_key)', status:'offline', lastPing:'2026-09-11 18:02', scripts:0}
  ],
  /* 运行时节点（/dep/runtime）：任务执行节点注册表，SSH 主机信息唯一权威源；RT01 为本地自动注册 */
  runtimeNodes: [
    {id:'RT01', name:'本地节点', kind:'本地', host:'localhost', port:22, user:'datara', auth:'本地进程（无需SSH）', runtimeDir:'/datara/runtime', tmpDir:'/datara/tmp', os:'容器内 Linux', status:'online', cpu:12, mem:34, disk:41, tasks:1, lastHeartbeat:'2026-09-12 22:20', desc:'随系统自动注册，无需 SSH 配置'},
    {id:'RT02', name:'批量同步执行节点', kind:'远程', host:'192.168.30.31', port:22, user:'datara', auth:'密钥(datara_key)', runtimeDir:'/home/datara/runtime', tmpDir:'/home/datara/tmp', os:'麒麟V10(鲲鹏920)', status:'online', cpu:46, mem:58, disk:63, tasks:2, lastHeartbeat:'2026-09-12 22:20'},
    {id:'RT03', name:'脚本备份节点', kind:'远程', host:'192.168.30.32', port:22, user:'datara', auth:'密码(加密存储)', runtimeDir:'/home/datara/runtime', tmpDir:'/data/tmp', os:'麒麟V10(鲲鹏920)', status:'online', cpu:18, mem:31, disk:47, tasks:0, lastHeartbeat:'2026-09-12 22:19'},
    {id:'RT04', name:'东信云前置机', kind:'远程', host:'10.20.8.15', port:22, user:'datara', auth:'密钥(vpn_key)', runtimeDir:'/home/datara/runtime', tmpDir:'/home/datara/tmp', os:'麒麟V10(x86)', status:'offline', cpu:0, mem:0, disk:52, tasks:0, lastHeartbeat:'2026-09-11 18:02'}
  ],
  /* 全局分发策略：启动/重跑任务时按策略挑选执行节点（runtimeService.pickExecNode） */
  runtimePolicy: {id:'RP01', mode:'轮询', specificNode:'', updatedAt:'2026-09-12 22:00'},

  /* ===== M16 部署 ===== */
  servers: [
    {id:'SV01', name:'master-01', ip:'192.168.30.10', cpu:'16C', mem:'64G', disk:'2T', os:'麒麟V10/鲲鹏920', role:'管理+部署', status:'online'},
    {id:'SV02', name:'node-01', ip:'192.168.30.11', cpu:'16C', mem:'64G', disk:'4T', os:'麒麟V10/鲲鹏920', role:'数据节点', status:'online'},
    {id:'SV03', name:'node-02', ip:'192.168.30.12', cpu:'16C', mem:'64G', disk:'4T', os:'麒麟V10/鲲鹏920', role:'数据节点', status:'online'},
    {id:'SV04', name:'node-03', ip:'192.168.30.13', cpu:'16C', mem:'64G', disk:'4T', os:'麒麟V10/鲲鹏920', role:'数据节点', status:'online'},
    {id:'SV05', name:'edge-01', ip:'10.20.8.15', cpu:'8C', mem:'32G', disk:'1T', os:'麒麟V10/x86', role:'前置机', status:'offline'}
  ],
  components: [
    {id:'CP01', name:'Apache Doris', version:'2.1.6', role:'实时数仓 OLAP', nodes:['192.168.30.10(FE)','192.168.30.11(BE)','192.168.30.12(BE)','192.168.30.13(BE)'], status:'running', health:'健康', cpu:38, mem:61, qps:420, upDays:23},
    {id:'CP02', name:'Kafka', version:'3.6.1', role:'消息队列', nodes:['192.168.30.11','192.168.30.12','192.168.30.13'], status:'running', health:'健康', cpu:24, mem:45, qps:6500, upDays:23},
    {id:'CP03', name:'Flink', version:'1.18.1', role:'流计算引擎', nodes:['192.168.30.10(JobManager)','192.168.30.11(TaskManager)','192.168.30.12(TaskManager)'], status:'running', health:'健康', cpu:52, mem:58, qps:0, upDays:18},
    {id:'CP04', name:'Zookeeper', version:'3.8.3', role:'协调服务', nodes:['192.168.30.11','192.168.30.12','192.168.30.13'], status:'running', health:'健康', cpu:5, mem:12, qps:0, upDays:23},
    {id:'CP05', name:'Redis', version:'7.2.4', role:'缓存', nodes:['192.168.30.10'], status:'running', health:'健康', cpu:8, mem:22, qps:1800, upDays:23},
    {id:'CP06', name:'Prometheus + Grafana', version:'2.52 / 10.4', role:'监控', nodes:['192.168.30.10'], status:'running', health:'健康', cpu:12, mem:28, qps:0, upDays:23},
    {id:'CP07', name:'RocketMQ', version:'-', role:'消息队列(国产备选)', nodes:[], status:'undeploy', health:'-', cpu:0, mem:0, qps:0, upDays:0},
    {id:'CP08', name:'HDFS + Hive', version:'-', role:'离线数仓', nodes:[], status:'undeploy', health:'-', cpu:0, mem:0, qps:0, upDays:0},
    {id:'CP09', name:'StarRocks', version:'-', role:'实时数仓 OLAP(国产开源)', nodes:[], status:'undeploy', health:'-', cpu:0, mem:0, qps:0, upDays:0},
    {id:'CP10', name:'Nacos', version:'-', role:'配置/注册中心', nodes:[], status:'undeploy', health:'-', cpu:0, mem:0, qps:0, upDays:0},
    {id:'CP11', name:'Spark', version:'-', role:'批处理引擎', nodes:[], status:'undeploy', health:'-', cpu:0, mem:0, qps:0, upDays:0}
  ],
  suites: [
    {id:'SU01', name:'实时数仓套件', comps:'Doris + Kafka + Flink + Zookeeper', desc:'实时数据入仓+流计算', status:'deployed'},
    {id:'SU02', name:'离线数仓套件', comps:'HDFS + Hive + Spark + 调度', desc:'离线批处理ETL', status:'undeploy'},
    {id:'SU03', name:'湖仓一体套件', comps:'Hudi/Iceberg + Spark + Flink + Doris', desc:'湖仓一体架构', status:'undeploy'},
    {id:'SU04', name:'监控运维套件', comps:'Prometheus + Grafana + AlertManager', desc:'全组件监控告警', status:'deployed'}
  ],
  deployWizardSteps: ['选择组件','选择节点','填写配置','前置检查','安装执行','健康检查'],
  precheckItems: [
    {item:'网络连通性(SSH 22端口)', result:'pass', detail:'4/4节点可达'},
    {item:'磁盘空间 ≥ 100G', result:'pass', detail:'最小可用 1.2T'},
    {item:'端口占用检查(9030/9092/8081)', result:'pass', detail:'无冲突'},
    {item:'依赖检查(JDK/时钟同步)', result:'warn', detail:'node-03 时钟偏差 4.2s，建议NTP校准'},
    {item:'OS兼容(麒麟V10/鲲鹏920)', result:'pass', detail:'全节点通过'}
  ],
  deployLogs: [
    {id:'DL01', comp:'Kafka', node:'192.168.30.12', time:'2026-09-12 21:40:22', level:'INFO', content:'[21:40:22] Partition reassignment completed (topic_order_pay, 6 partitions)'},
    {id:'DL02', comp:'Doris', node:'192.168.30.20', time:'2026-09-12 21:38:02', level:'WARN', content:'[21:38:02] tablet 10230 replica backends not healthy, will try to fix in 60s'},
    {id:'DL03', comp:'Flink', node:'192.168.30.10', time:'2026-09-12 21:35:40', level:'INFO', content:'[21:35:40] Completed checkpoint 12845 for job 订单支付实时入仓 (6012 ms)'},
    {id:'DL04', comp:'Doris', node:'192.168.30.11', time:'2026-09-12 21:30:11', level:'ERROR', content:'[21:30:11] BE 10002 heartbeat timeout from FE, retry 1/3 (已自恢复)'},
    {id:'DL05', comp:'Prometheus', node:'192.168.30.10', time:'2026-09-12 21:20:00', level:'INFO', content:'[21:20:00] rule evaluation took 1.2s, 42 series loaded'}
  ],
  deployAlarms: [
    {id:'PA01', level:'warn', comp:'Doris', title:'BE节点磁盘使用率 82%', time:'2026-09-12 20:15', channel:'邮件', status:'pending', desc:'192.168.30.13 磁盘 82%，阈值 80%'},
    {id:'PA02', level:'err', comp:'Kafka', title:'消费组 lag 突增', time:'2026-09-12 19:02', channel:'邮件+短信', status:'fixed', desc:'topic_order_pay 消费组 datara-flink lag 12万（瞬时），已恢复'},
    {id:'PA03', level:'info', comp:'Flink', title:'Checkpoint 耗时偏高', time:'2026-09-12 17:40', channel:'邮件', status:'fixed', desc:'SJ002 checkpoint 18s→42s，已扩并行度恢复'}
  ],
  backups: [
    {id:'BK01', target:'Doris 元数据+配置', time:'2026-09-12 03:00', size:'2.1GB', type:'自动(每日)', status:'success'},
    {id:'BK02', target:'Kafka 配置', time:'2026-09-12 03:00', size:'12MB', type:'自动(每日)', status:'success'},
    {id:'BK03', target:'平台配置库全量', time:'2026-09-11 03:00', size:'860MB', type:'自动(每日)', status:'success'}
  ],
  ideHistory: [
    {id:'H001', ds:'DS006', sql:'SELECT channel, pay_amount_sum FROM dws_pay_summary_daily WHERE dt = \'2026-09-11\'', rows:2, dur:'0.31s', time:'2026-09-12 21:02', star:true},
    {id:'H002', ds:'DS001', sql:'SELECT COUNT(*) FROM ods_gdb_biz_trade_order WHERE dt=\'2026-09-11\'', rows:1, dur:'0.86s', time:'2026-09-12 10:15', star:false},
    {id:'H003', ds:'DS002', sql:'SELECT * FROM BUDGET_YEAR LIMIT 100', rows:100, dur:'1.24s', time:'2026-09-11 16:40', star:true}
  ],
  sqlFuncs: [
    {cat:'聚合函数', items:['SUM(expr) 求和','COUNT(1) 计数','COUNT(DISTINCT x) 去重计数','AVG(expr) 平均','MAX/MIN(expr) 最值']},
    {cat:'字符串函数', items:['CONCAT(a,b) 拼接','SUBSTR(s,p,l) 截取','UPPER/LOWER(s) 大小写','TRIM(s) 去空格','REPLACE(s,a,b) 替换','LENGTH(s) 长度']},
    {cat:'日期函数', items:['CURRENT_DATE 当前日期','DATE_SUB(d,N) 减N天','DATE_FORMAT(d,f) 格式化','TO_DATE(s) 转日期','DATEDIFF(a,b) 差值']},
    {cat:'数学函数', items:['ROUND(x,n) 四舍五入','ABS(x) 绝对值','CEIL/FLOOR(x) 取整','MOD(a,b) 取模']},
    {cat:'窗口函数', items:['ROW_NUMBER() OVER(...) 行号','RANK()/DENSE_RANK() 排名','SUM() OVER(...) 窗口聚合','LAG/LEAD(x,n) 偏移','NTILE(n) 分桶']}
  ],
  lineageGraph: {
  nodes: [
    {id:'ods_gdb_biz_user_info', layer:'ODS'},
    {id:'ods_gdb_biz_pay_record', layer:'ODS'},
    {id:'ods_gdb_biz_trade_order', layer:'ODS'},
    {id:'ods_oracle_gl_voucher', layer:'ODS'},
    {id:'ods_mysql_product_info', layer:'ODS'},
    {id:'dim_user', layer:'DIM'},
    {id:'dwd_order_pay_detail', layer:'DWD'},
    {id:'dwd_gl_voucher_detail', layer:'DWD'},
    {id:'dws_pay_summary_daily', layer:'DWS'},
    {id:'ads_kpi_report', layer:'ADS'}
  ],
  edges: [
    ['ods_gdb_biz_user_info','dim_user'],
    ['ods_gdb_biz_pay_record','dwd_order_pay_detail'],
    ['ods_gdb_biz_trade_order','dwd_order_pay_detail'],
    ['dim_user','dwd_order_pay_detail'],
    ['dwd_order_pay_detail','dws_pay_summary_daily'],
    ['dws_pay_summary_daily','ads_kpi_report'],
    ['ods_oracle_gl_voucher','dwd_gl_voucher_detail'],
    ['ods_mysql_product_info','dwd_order_pay_detail']
  ]
  }
};
/* ---------- IDataStore 内存实现（localStorage 兜底，复制 graphService lsTry 模式） ---------- */
class MemoryDataStore implements IDataStore {
  private map = new Map<CollectionKey, unknown[]>()

  constructor(seed: Record<string, unknown>) {
    for (const [k, v] of Object.entries(seed)) {
      const key = k as CollectionKey
      this.map.set(key, this.load(key) ?? (Array.isArray(v) ? v : [v]))
    }
  }

  async get<T>(col: CollectionKey): Promise<T | null> {
    const rows = this.map.get(col)
    if (!rows || rows.length === 0) return null
    return rows[0] as T
  }

  async list<T>(col: CollectionKey): Promise<T[]> {
    return (this.map.get(col) ?? []) as T[]
  }

  async save<T>(col: CollectionKey, row: T): Promise<void> {
    const rows = this.map.get(col) ?? []
    const id = (row as { id?: string | number }).id
    if (id != null) {
      const i = rows.findIndex((r) => (r as { id?: string | number }).id === id)
      if (i >= 0) rows[i] = row
      else rows.push(row)
    } else {
      rows.push(row)
    }
    this.map.set(col, rows)
    this.persist(col)
  }

  async remove(col: CollectionKey, id: string): Promise<void> {
    const rows = this.map.get(col) ?? []
    this.map.set(col, rows.filter((r) => (r as { id?: string | number }).id !== id))
    this.persist(col)
  }

  private load(col: CollectionKey): unknown[] | null {
    try {
      const raw = localStorage.getItem(`datara.db.${col}`)
      if (!raw) return null
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed : null
    } catch {
      return null
    }
  }

  private persist(col: CollectionKey): void {
    try {
      localStorage.setItem(`datara.db.${col}`, JSON.stringify(this.map.get(col)))
    } catch {
      /* 忽略持久化失败（内存态继续可用） */
    }
  }
}

export const dataStore: IDataStore = new MemoryDataStore(DB)