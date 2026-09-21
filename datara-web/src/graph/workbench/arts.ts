/**
 * 拓扑设备图标库（内联 SVG path 片段，24×24 viewBox，stroke=currentColor）。
 * 供 topo profile 设备形态节点使用：主机 / 交换机 / 服务器 / 防火墙 /
 * ZooKeeper、Kafka、Redis、Spark、Flink、MySQL、HDFS、Doris 等中间件 logo 风格图标。
 * DataNode 以 <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">+v-html 渲染。
 */
export const NODE_ART: Record<string, string> = {
  /* ── 通用设备 ── */
  /** 主机（工作站） */
  host: '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4M7 8h6M7 11h4"/>',
  /** 交换机（机框 + 端口 + 转发箭头） */
  switch: '<rect x="2.5" y="7.5" width="19" height="9" rx="1.5"/><path d="M5.5 10.5v3M8 10.5v3M10.5 10.5v3M13 10.5v3"/><path d="M16 12h3.5m0 0-1.6-1.6M19.5 12l-1.6 1.6"/>',
  /** 服务器（双机架 + 指示灯） */
  server: '<rect x="3" y="3.5" width="18" height="7.5" rx="1.2"/><rect x="3" y="13" width="18" height="7.5" rx="1.2"/><circle cx="6.2" cy="7.2" r=".5"/><circle cx="6.2" cy="16.8" r=".5"/><path d="M10 7.2h8M10 16.8h8"/>',
  /** 防火墙（砖墙） */
  firewall: '<rect x="3" y="5" width="18" height="14" rx="1.2"/><path d="M3 12h18M8 5v7M13.5 5v7M8 12v7M15 12v7M13.5 8.5H18M3 8.5h3"/>',
  /** 负载均衡（交换机形态 + 三向分流） */
  lb: '<rect x="2.5" y="8.5" width="19" height="7" rx="1.5"/><path d="M5.5 10.8v2.4M8 10.8v2.4M10.5 10.8v2.4"/><path d="M14.5 12h5m0 0-1.7-1.7M19.5 12l-1.7 1.7M14.5 9V6.2M14.5 15v2.8"/>',

  /* ── 平台组件 ── */
  /** API 网关（门形 + 入站箭头） */
  gateway: '<path d="M4.5 20V9a7.5 7.5 0 0 1 15 0v11"/><path d="M4.5 20h15"/><path d="M8.5 12h5.5m0 0-1.8-1.8M14 12l-1.8 1.8"/>',
  /** 调度 Master（服务器 + 中心控制点） */
  ds_master: '<rect x="3" y="3.5" width="18" height="7.5" rx="1.2"/><rect x="3" y="13" width="18" height="7.5" rx="1.2"/><path d="M10 7.2h8M10 16.8h8"/><circle cx="12" cy="11.9" r="1.6" fill="currentColor" stroke="none"/><path d="M12 10.3V8.4M12 13.5v2"/>',
  /** 执行 Worker（三机架） */
  ds_worker: '<rect x="4" y="2.8" width="16" height="4.6" rx="1"/><rect x="4" y="9.7" width="16" height="4.6" rx="1"/><rect x="4" y="16.6" width="16" height="4.6" rx="1"/><circle cx="6.6" cy="5.1" r=".5"/><circle cx="6.6" cy="12" r=".5"/><circle cx="6.6" cy="18.9" r=".5"/><path d="M9.5 5.1h7.5M9.5 12h7.5M9.5 18.9h7.5"/>',
  /** 应用实例（机架服务器） */
  app: '<rect x="3" y="3.5" width="18" height="7.5" rx="1.2"/><rect x="3" y="13" width="18" height="7.5" rx="1.2"/><circle cx="6.2" cy="7.2" r=".5"/><circle cx="6.2" cy="16.8" r=".5"/><path d="M10 7.2h8M10 16.8h8"/>',

  /* ── 中间件（logo 风格） ── */
  /** ZooKeeper（圆环 + Z） */
  zk: '<circle cx="12" cy="12" r="8.5"/><path d="M9 9.2h6l-6 5.6h6"/>',
  /** Kafka（圆 + 三向散射横道） */
  kafka: '<circle cx="6.8" cy="12" r="3" fill="currentColor" stroke="none"/><path d="M10.2 12H20M10 10.6 19 5.6M10 13.4l9 5"/><path d="M17.5 5.6v.01M17.5 18.4v.01M20 12v.01" stroke-width="2.2"/>',
  /** Redis（三层堆叠块） */
  redis: '<path d="M12 3.5l8 3.2-8 3.2-8-3.2z"/><path d="M4 11.2l8 3.2 8-3.2M4 15.8 12 19l8-3.2"/>',
  /** Spark（四角星芒，实心） */
  spark: '<path d="M12 2.5l2.3 7.2 7.2 2.3-7.2 2.3L12 21.5l-2.3-7.2-7.2-2.3 7.2-2.3z" fill="currentColor" stroke="none"/>',
  /** Flink（三重波浪） */
  flink: '<path d="M3.5 7.2c2.8-1.8 5.7-1.8 8.5 0s5.7 1.8 8.5 0M3.5 12c2.8-1.8 5.7-1.8 8.5 0s5.7 1.8 8.5 0M3.5 16.8c2.8-1.8 5.7-1.8 8.5 0s5.7 1.8 8.5 0"/>',
  /** MySQL / GreatDB（数据库圆柱） */
  mysql: '<ellipse cx="12" cy="5.5" rx="8" ry="2.6"/><path d="M4 5.5V18.5c0 1.4 3.6 2.6 8 2.6s8-1.2 8-2.6V5.5"/><path d="M4 12c0 1.4 3.6 2.6 8 2.6s8-1.2 8-2.6"/>',
  /** HDFS（三层数据块） */
  hdfs: '<rect x="5" y="3.5" width="14" height="4.6" rx="1"/><rect x="5" y="9.7" width="14" height="4.6" rx="1"/><rect x="5" y="15.9" width="14" height="4.6" rx="1"/><path d="M8 5.8h.01M8 12h.01M8 18.2h.01" stroke-width="2.2"/>',
  /** Doris（三维立方体） */
  doris: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12 4 7.5M12 12v9"/>',
}

/** 设备形态默认图标（未知类型兜底：服务器） */
export const NODE_ART_FALLBACK = NODE_ART.server
