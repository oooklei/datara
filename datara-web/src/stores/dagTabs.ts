import { defineStore } from 'pinia'

/**
 * I11 画布多 Tab store（用户裁定：同一个画布同时只能编辑一个工作流；
 * 多个工作流用 tab 切换，每个 tab 可关闭（关闭时提示保存），最多同时打开 5 个；
 * 每载入一个工作流增加 1 个画布 tab）。
 *
 * 宿主（TaskCenterView）持有 tabs 数组，以 :key 重挂载 GraphWorkbench 单实例；
 * 同一 docId 只允许一个 tab（重复载入 = 激活已有 tab）。
 */
export type DagProfileType = 'wf' | 'sync' | 'etl' | 'stream'

export interface DagTab {
  /** = docId（同一工作流只开一个 tab，天然唯一） */
  key: string
  docId: string
  name: string
  type: DagProfileType
  /** I11：数字编码（画布标题 #code / 目录 / 名称） */
  code?: number
}

/** 画布 Tab 上限（用户裁定：同时只能打开 5 个） */
export const MAX_DAG_TABS = 5

/** Palette「载入选中」载荷项：宿主逐项开画布 Tab（type 决定视角 Profile，code 供标题 #code） */
export interface DagPickItem {
  id: string
  name: string
  type: DagProfileType
  code?: number
}

export const useDagTabsStore = defineStore('dagTabs', {
  state: () => ({
    tabs: [] as DagTab[],
    activeKey: '',
  }),
  getters: {
    activeTab(state): DagTab | null {
      return state.tabs.find((t) => t.key === state.activeKey) ?? null
    },
    count: (s) => s.tabs.length,
  },
  actions: {
    isOpen(docId: string): boolean {
      return this.tabs.some((t) => t.docId === docId)
    },
    /** 打开（或激活已有）工作流 Tab。返回 'ok' | 'dup'（已开仅激活）| 'full'（超 5 拒绝） */
    open(tab: Omit<DagTab, 'key'>): 'ok' | 'dup' | 'full' {
      const existing = this.tabs.find((t) => t.docId === tab.docId)
      if (existing) {
        this.activate(existing.key)
        return 'dup'
      }
      if (this.tabs.length >= MAX_DAG_TABS) return 'full'
      this.tabs.push({ ...tab, key: tab.docId })
      this.activate(tab.docId)
      return 'ok'
    },
    activate(key: string) {
      if (this.tabs.some((t) => t.key === key)) this.activeKey = key
    },
    /**
     * 移除 tab（宿主需先完成「保存 / 放弃 / 取消」三选与快照清理，此处仅收尾）。
     * 返回被移除 tab 的 docId（供宿主清理其草稿快照）；不存在返回 null。
     */
    remove(key: string): string | null {
      const idx = this.tabs.findIndex((t) => t.key === key)
      if (idx < 0) return null
      const [removed] = this.tabs.splice(idx, 1)
      if (this.activeKey === key) {
        const next = this.tabs[Math.min(idx, this.tabs.length - 1)]
        this.activeKey = next ? next.key : ''
      }
      return removed?.docId ?? null
    },
  },
})