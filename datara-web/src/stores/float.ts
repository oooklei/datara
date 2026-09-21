import { defineStore } from 'pinia'
import { markRaw, type Component } from 'vue'

export interface FloatWin {
  id: string
  title: string
  x: number
  y: number
  w: number
  h: number
  minimized: boolean
  comp: Component
  props?: Record<string, unknown>
  /** 渲染层级（open 时自动分配） */
  z?: number
}

/** 浮窗框架状态：可拖动/收起/单例（同 id 复用并置顶） */
export const useFloatStore = defineStore('float', {
  state: () => ({
    floats: [] as FloatWin[],
    zTop: 2500,
  }),
  actions: {
    open(win: Omit<FloatWin, 'z'>) {
      const comp = markRaw(win.comp) // 避免组件对象被 reactive 包装（Vue warn）
      const exist = this.floats.find((f) => f.id === win.id)
      this.zTop += 1
      if (exist) {
        Object.assign(exist, { ...win, comp, x: exist.x, y: exist.y, minimized: false, z: this.zTop })
        return
      }
      this.floats.push({ ...win, comp, minimized: false, z: this.zTop })
    },
    close(id: string) {
      this.floats = this.floats.filter((f) => f.id !== id)
    },
    toggleMin(id: string) {
      const f = this.floats.find((x) => x.id === id)
      if (f) f.minimized = !f.minimized
    },
    focus(id: string) {
      this.zTop += 1
      const f = this.floats.find((x) => x.id === id)
      if (f) f.z = this.zTop
    },
    move(id: string, x: number, y: number) {
      const f = this.floats.find((x2) => x2.id === id)
      if (f) { f.x = x; f.y = y }
    },
  },
})
