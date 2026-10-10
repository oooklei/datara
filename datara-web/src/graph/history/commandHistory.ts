import { defineStore } from 'pinia'
import type { GraphDocument } from '../model'
import type { GraphCommand } from './commands'

/** 命令栈容量（与 graph.ts 快照栈 HISTORY_CAP 对齐，防大图内存膨胀；命令各持前后档两份克隆） */
const COMMAND_CAP = 50

/**
 * Task 22（2e / 方案§3.5）：undo 命令栈（灰度开关 undoCommandStack=on 时的历史通道）。
 * 快照栈（graphStore.undoStack）保留兜底：off 时 undo/redo 仍走快照栈，行为不变。
 *
 * 命令由 GraphWorkbench 在六类变更点（AddNode/DeleteNodes/MoveNodes/Connect/Disconnect/
 * UpdateProps）捕获前后档压入；undo/redo 经 cmd.undo/apply 换档，GraphWorkbench 负责把
 * 返回档换入 graphStore（setDocViaCommand，不触碰快照栈）并重同步画布。
 */
export const useCommandHistory = defineStore('graphCommandHistory', {
  state: () => ({
    undoStack: [] as GraphCommand[],
    redoStack: [] as GraphCommand[],
  }),
  getters: {
    canUndo: (s) => s.undoStack.length > 0,
    canRedo: (s) => s.redoStack.length > 0,
  },
  actions: {
    /** 新变更入栈（清空 redo，与快照栈语义一致）；超限挤掉最旧命令 */
    push(cmd: GraphCommand) {
      this.undoStack.push(cmd)
      if (this.undoStack.length > COMMAND_CAP) this.undoStack.shift()
      this.redoStack = []
    },
    /** 撤销：返回恢复档（无命令可撤返回 null）；被撤命令让位给 redo */
    undo(doc: GraphDocument): GraphDocument | null {
      const cmd = this.undoStack.pop()
      if (!cmd) return null
      const prev = cmd.undo(doc)
      this.redoStack.push(cmd)
      return prev
    },
    /** 重做：返回重放档（无命令可重做返回 null）；命令归位 undo 栈 */
    redo(doc: GraphDocument): GraphDocument | null {
      const cmd = this.redoStack.pop()
      if (!cmd) return null
      const next = cmd.apply(doc)
      this.undoStack.push(cmd)
      return next
    },
    /** 整档替换（载入/保存换版/自动布局/外部回滚等）后历史失配 → 清空（由宿主在换档点调用） */
    reset() {
      this.undoStack = []
      this.redoStack = []
    },
  },
})
