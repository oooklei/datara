/**
 * 「后续批次」折叠组机制（增量 2 / 票 2-04）
 *
 * 蓝本：0.8 方案 §5（L136-170）——复用旧框架 foldable 折叠交互语义（旧实锚 App.vue
 * L121-122 折叠状态 ref + toggle、L425-429 caret 样式；§5D 三层调和：复刻语义与布局，
 * 不复制旧实现代码），不复用 demo 标签及演示数据含义。
 * 纪律：
 *  - 折叠状态持久化用稳定键（组 id），禁用可变中文标签作键（0.8 L161 / 拆票 R5 防漂移）
 *  - 空组整组隐藏由 filterMenuGroups 保证（eligibleFutureItems 为空不产出 future 组，2-02）；
 *    本模块只管折叠态，组是否渲染由过滤层决定
 *  - 展开仅翻转折叠态并持久化，不触碰路由（「展开不改路由」，0.8 §7 测试集 4）
 *  - 转正保持同一 id（0.8 §5.3）：future 项转正后 id 不变，本模块键随组 id 恒定
 */

const KEY_PREFIX = 'datara.menu.groupFolded.'

/** 折叠态存储键（稳定键=组 id；R5：禁中文标签防转正/重命名漂移） */
export function groupFoldKey(groupId: string): string {
  if (/[\u4e00-\u9fff]/.test(groupId)) {
    throw new Error(`groupFoldKey: 稳定键禁中文标签（收到 "${groupId}"）——0.8 L161/R5 键漂移守卫`)
  }
  return KEY_PREFIX + groupId
}

/** 读取折叠态：无存储或缺省时返回 defaultFolded（future 组 menu.ts 冻结 true） */
export function loadGroupFolded(groupId: string, defaultFolded: boolean): boolean {
  if (typeof localStorage === 'undefined') return defaultFolded
  const raw = localStorage.getItem(groupFoldKey(groupId))
  if (raw === '1') return true
  if (raw === '0') return false
  return defaultFolded
}

/** 持久化折叠态 */
export function saveGroupFolded(groupId: string, folded: boolean): void {
  if (typeof localStorage === 'undefined') return
  localStorage.setItem(groupFoldKey(groupId), folded ? '1' : '0')
}

/** 翻转折叠态并持久化（旧 toggleGroup 语义；仅折叠态，零路由副作用） */
export function toggleGroupFolded(groupId: string, currentFolded: boolean): boolean {
  const next = !currentFolded
  saveGroupFolded(groupId, next)
  return next
}
