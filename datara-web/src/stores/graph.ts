import { defineStore } from 'pinia'
import type { GraphDocument } from '../graph/model'
import { graphService } from '../services'

/** F56b N14：历史栈容量（快照步数上限，防大图内存膨胀） */
const HISTORY_CAP = 50

/**
 * 图文档 store：load/save + 脏标记 + F56b N14 撤销/重做。
 * 历史以 JSON 快照实现（文档均为可序列化 JSON，规模为几十节点级，开销可忽略）：
 * - markDirty()：变更后调用，把上一快照压入 undo 栈、清空 redo 栈；
 * - replace()：整档替换（自动布局/Inspector 重同步）视作一次变更入栈；
 * - undo()/redo()：换档恢复引用（GraphWorkbench watch(graphStore.doc) 自动重同步画布）。
 */
export const useGraphStore = defineStore('graph', {
  state: () => ({
    doc: null as GraphDocument | null,
    dirty: false,
    saving: false,
    /* N14 快照栈：undoStack 存历史态、redoStack 存被撤销态、lastSnap 为最近基线 */
    undoStack: [] as string[],
    redoStack: [] as string[],
    lastSnap: '',
  }),
  getters: {
    canUndo: (s) => s.undoStack.length > 0,
    canRedo: (s) => s.redoStack.length > 0,
  },
  actions: {
    async load(id: string) {
      this.doc = await graphService.get(id)
      this.dirty = false
      this.resetHistory()
    },
    async save(remark?: string) {
      if (!this.doc) return 0
      this.saving = true
      try {
        const { version } = await graphService.save(this.doc, remark)
        this.doc = { ...this.doc, version }
        this.dirty = false
        /* 保存点刷新基线（不清历史：保存后仍可撤销到保存前） */
        this.lastSnap = JSON.stringify(this.doc)
        return version
      } finally {
        this.saving = false
      }
    },
    markDirty() {
      this.dirty = true
      const snap = JSON.stringify(this.doc)
      if (snap === this.lastSnap) return // 幂等标记（如运行检查后的重同步）不入栈
      if (this.lastSnap) {
        this.undoStack.push(this.lastSnap)
        if (this.undoStack.length > HISTORY_CAP) this.undoStack.shift()
      }
      this.redoStack = []
      this.lastSnap = snap
    },
    /** 局部更新（保持引用响应性）；整档替换视作一次变更入历史栈 */
    replace(doc: GraphDocument) {
      if (this.doc) {
        const prev = JSON.stringify(this.doc)
        if (prev !== JSON.stringify(doc)) {
          this.undoStack.push(prev)
          if (this.undoStack.length > HISTORY_CAP) this.undoStack.shift()
          this.redoStack = []
        }
      }
      this.doc = doc
      this.dirty = true
      this.lastSnap = JSON.stringify(doc)
    },
    /** 外部构建文档注入（血缘等只读视图）：不置脏、不持久化、重置历史 */
    setDoc(doc: GraphDocument) {
      this.doc = doc
      this.dirty = false
      this.resetHistory()
    },
    /** 撤销：恢复上一快照；返回是否执行 */
    undo(): boolean {
      const prev = this.undoStack.pop()
      if (!prev || !this.doc) return false
      this.redoStack.push(JSON.stringify(this.doc))
      this.doc = JSON.parse(prev)
      this.dirty = true
      this.lastSnap = prev
      return true
    },
    /** 重做：恢复被撤销态；返回是否执行 */
    redo(): boolean {
      const next = this.redoStack.pop()
      if (!next || !this.doc) return false
      this.undoStack.push(JSON.stringify(this.doc))
      this.doc = JSON.parse(next)
      this.dirty = true
      this.lastSnap = next
      return true
    },
    resetHistory() {
      this.undoStack = []
      this.redoStack = []
      this.lastSnap = this.doc ? JSON.stringify(this.doc) : ''
    },
  },
})
