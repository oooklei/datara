import { defineStore } from 'pinia'
import { toRaw } from 'vue'
import type { GraphDocument } from '../graph/model'
import { graphService } from '../services'

/** F56b N14：历史栈容量（快照步数上限，防大图内存膨胀） */
const HISTORY_CAP = 50

/** Task 14 审查修复：load 时序序号（模块级计数——graphStore 为全局单例，keep-alive 下多画布实例共用） */
let loadSeq = 0

/**
 * 图文档 store：load/save + 脏标记 + F56b N14 撤销/重做。
 * Task 12（§3.6）双轨历史：JSON.stringify 快照串（lastSnap）仅作幂等对比基线，
 * 栈内改存深拷贝对象，undo/redo 直接换引用，不再 JSON.parse。
 *
 * 不变量（钉死）：lastDoc ≡ lastSnap 字符串对应时刻的深拷贝；
 * 所有刷新 lastSnap 的路径（markDirty/replace/save/resetHistory/undo/redo）必须同步刷新 lastDoc。
 * 克隆来源均为纯对象树（reactive 代理树不可 structuredClone，且 stringify 可穿透代理）：
 * - 基线克隆 = JSON.parse(已算好的快照串)：零额外 stringify，天然纯对象；
 * - undo/redo 恢复 = structuredClone(toRaw(栈内纯克隆))：与栈/基线无别名，
 *   撤销态上就地编辑不会污染历史（store 的 reactive 深代理只会包一层，toRaw 一次即得纯树）。
 * - markDirty()：变更后调用，把上一基线克隆压入 undo 栈、清空 redo 栈；
 * - replace()：整档替换（自动布局/Inspector 重同步）视作一次变更入栈；
 * - undo()/redo()：换档恢复引用（GraphWorkbench watch(graphStore.doc) 自动重同步画布）。
 */
export const useGraphStore = defineStore('graph', {
  state: () => ({
    doc: null as GraphDocument | null,
    dirty: false,
    saving: false,
    /* N14 快照栈（Task 12 起存深拷贝对象）：undoStack 存历史态、redoStack 存被撤销态、lastSnap 为最近基线串 */
    undoStack: [] as GraphDocument[],
    redoStack: [] as GraphDocument[],
    lastSnap: '',
    /* Task 12（§3.6）：lastSnap 对应时刻的深拷贝基线（与 lastSnap 恒同步，见上方不变量） */
    lastDoc: null as GraphDocument | null,
  }),
  getters: {
    canUndo: (s) => s.undoStack.length > 0,
    canRedo: (s) => s.redoStack.length > 0,
  },
  actions: {
    async load(id: string) {
      /* Task 14 审查修复：时序守卫——keep-alive 下多画布实例共存且 store 为全局单例，
       * 快速 A→B→A 切 Tab 时两次 load 并发在途，先发出的旧响应可能晚到，把 doc 覆盖回旧档
       * （后续读写全落在错误文档上）。发号后比对：await 期间已有更新的 load 发起（seq !== loadSeq）
       * 则本次响应整体丢弃——不写 doc、不置 dirty、不动 lastSnap/历史栈，终态由最新一次 load 负责。
       * 返回是否真正落档（旧响应丢弃返回 false），调用方均 await 忽略返回值，向后兼容。 */
      const seq = ++loadSeq
      const doc = await graphService.get(id)
      if (seq !== loadSeq) return false
      this.doc = doc
      this.dirty = false
      this.resetHistory()
      return true
    },
    async save(remark?: string) {
      if (!this.doc) return 0
      this.saving = true
      try {
        const { version } = await graphService.save(this.doc, remark)
        this.doc = { ...this.doc, version }
        this.dirty = false
        /* 保存点刷新基线（不清历史：保存后仍可撤销到保存前）；lastSnap 与 lastDoc 恒同步 */
        this.lastSnap = JSON.stringify(this.doc)
        this.lastDoc = JSON.parse(this.lastSnap)
        return version
      } finally {
        this.saving = false
      }
    },
    markDirty() {
      this.dirty = true
      const snap = JSON.stringify(this.doc)
      if (snap === this.lastSnap) return // 幂等标记（如运行检查后的重同步）不入栈
      if (this.lastDoc) {
        this.undoStack.push(this.lastDoc)
        if (this.undoStack.length > HISTORY_CAP) this.undoStack.shift()
      }
      this.redoStack = []
      this.lastSnap = snap
      this.lastDoc = JSON.parse(snap) // 复用快照串出纯克隆，零额外 stringify
    },
    /** 局部更新（保持引用响应性）；整档替换视作一次变更入历史栈 */
    replace(doc: GraphDocument) {
      if (this.doc) {
        const prevSnap = JSON.stringify(this.doc)
        if (prevSnap !== JSON.stringify(doc)) {
          this.undoStack.push(JSON.parse(prevSnap)) // 替换前态纯克隆入栈
          if (this.undoStack.length > HISTORY_CAP) this.undoStack.shift()
          this.redoStack = []
        }
      }
      this.doc = doc
      this.dirty = true
      this.lastSnap = JSON.stringify(doc)
      this.lastDoc = JSON.parse(this.lastSnap)
    },
    /** 外部构建文档注入（血缘等只读视图）：不置脏、不持久化、重置历史 */
    setDoc(doc: GraphDocument) {
      this.doc = doc
      this.dirty = false
      this.resetHistory()
    },
    /** Task 22（undoCommandStack=on）：命令栈 undo/redo 的整档换入——仅换引用 + 同步刷新基线
     *  （lastSnap/lastDoc 恒同步不变量），不动快照栈（历史由命令栈负责，快照栈保留兜底） */
    setDocViaCommand(doc: GraphDocument) {
      this.doc = doc
      this.dirty = true
      this.lastSnap = JSON.stringify(doc)
      this.lastDoc = JSON.parse(this.lastSnap)
    },
    /** 撤销：恢复上一快照；返回是否执行 */
    undo(): boolean {
      const prev = this.undoStack.pop()
      if (!prev || !this.doc || !this.lastDoc) return false
      this.redoStack.push(this.lastDoc) // 当前基线克隆让位给 redo（不变量保证 ≡ 当前态）
      /* 独立深拷贝恢复：与栈/基线无别名，撤销态上就地编辑不污染历史 */
      this.doc = structuredClone(toRaw(prev))
      this.dirty = true
      this.lastSnap = JSON.stringify(this.doc)
      this.lastDoc = prev
      return true
    },
    /** 重做：恢复被撤销态；返回是否执行（与 undo 对称） */
    redo(): boolean {
      const next = this.redoStack.pop()
      if (!next || !this.doc || !this.lastDoc) return false
      this.undoStack.push(this.lastDoc) // 当前基线克隆让位给 undo
      this.doc = structuredClone(toRaw(next))
      this.dirty = true
      this.lastSnap = JSON.stringify(this.doc)
      this.lastDoc = next
      return true
    },
    resetHistory() {
      this.undoStack = []
      this.redoStack = []
      this.lastSnap = this.doc ? JSON.stringify(this.doc) : ''
      this.lastDoc = this.doc ? JSON.parse(this.lastSnap) : null
    },
  },
})
