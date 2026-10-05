/**
 * 组件规格缓存 store（工作台优化 Task 4，方案 §2.3）。
 *
 * 职责：消费 GET /components/spec（componentApi.fetchComponentSpec，独立 fetch、
 * ETag/304 条件请求），把后端 8 要素骨架展平为 ComponentSpec 编辑形态并归一化缓存，
 * 供画布/页面设计器离线装配；服务不可用时置 degraded，消费方回落 profile 兜底。
 *
 * 缓存语义：
 * - specMap 以骨架 item.type 为键（ComponentSpec 本身无 type 字段）；
 * - 304 沿用现有缓存（specMap/etag 均不动），200 重建；
 * - 异常时 degraded=true、loaded 保持原值——loaded=false 的失败不计入首次加载，
 *   下次 ensureSpecs 自动重试；已加载过的失败不清缓存（旧规格继续可用）；
 * - invalidate() 等价 force 重拉，供事件广播与消费方主动失效使用；
 * - loading 中收到的 force 不被并发去重吞掉：记 pendingForce，在飞请求落地后补拉一次
 *   （否则本次发布要等下一次广播才可见）。
 */
import { markRaw } from 'vue'
import { defineStore } from 'pinia'
import { fetchComponentSpec, type ComponentSpecItem } from '../services/componentApi'
import { normalizeSpec, type ComponentSpec } from '../services/componentSpec'
import { bus } from '../services/eventBus'

/** 8 要素骨架 → 编辑形态展平（normalizeSpec 消费的顶层键；纯函数）。
 *  键映射对齐后端 _spec_item：identity.displayName/aliases、description.*、
 *  inputs→fields、visual.icon/color/badge；item.type 作 specMap 键、identity.type
 *  为冗余、visual.shape 无 ComponentSpec 对应位（均不进展平结果）。 */
function flattenSpecItem(it: ComponentSpecItem): Record<string, unknown> {
  return {
    displayName: it.identity.displayName,
    aliases: it.identity.aliases,
    summary: it.description.summary,
    description: it.description.description,
    category: it.description.category,
    docUrl: it.description.docUrl,
    fields: it.inputs,
    outputs: it.outputs,
    icon: it.visual.icon,
    color: it.visual.color,
    badge: it.visual.badge,
    behaviors: it.behaviors,
    dropPolicy: it.dropPolicy,
    extensions: it.extensions,
    specVersion: it.specVersion,
    ports: it.ports,
  }
}

export const useComponentStore = defineStore('component', {
  state: () => ({
    /** type → 归一化 spec（编辑形态） */
    specMap: new Map<string, ComponentSpec>(),
    /** 规格清单 ETag（If-None-Match 条件请求凭证） */
    etag: '',
    /** 首次拉取完成（200/304 成功往返后为 true） */
    loaded: false,
    /** 拉取进行中（并发去重） */
    loading: false,
    /** 内部标记：loading 中收到 force → 记账，在飞请求落地后补拉一次（防失效被去重吞掉） */
    pendingForce: false,
    /** 服务不可用降级标记：true → 消费方走 profile 兜底 */
    degraded: false,
  }),
  actions: {
    async ensureSpecs(force = false): Promise<void> {
      if (this.loaded && !force) return
      if (this.loading) {
        // force 撞上在飞请求：记待补拉标记而非直接吞掉——否则本次发布要等下一次广播才可见
        if (force) this.pendingForce = true
        return
      }
      this.loading = true
      try {
        const res = await fetchComponentSpec(this.etag || undefined)
        if (res === null) {
          // 304：服务端清单未变，specMap/etag 原样沿用（缓存价值所在）
        } else {
          // 200：整体重建（避免逐项 diff 的复杂度；清单规模 = 已发布组件数）。
          // markRaw：纯数据只读 + 整体替换，免去深 reactive 代理开销（float.ts 同模式先例）
          const map = new Map<string, ComponentSpec>()
          for (const it of res.items) map.set(it.type, markRaw(normalizeSpec(flattenSpecItem(it))))
          this.specMap = map
          this.etag = res.etag
        }
        this.degraded = false
        this.loaded = true
      } catch (err) {
        // 服务不可用 → 降级：loaded 保持原值（false 时下次自动重试），已缓存规格不清
        console.warn('[componentStore] 规格拉取失败，降级 profile 兜底', err)
        this.degraded = true
      } finally {
        this.loading = false
        if (this.pendingForce) {
          // 补拉一次失效重拉：此刻 loading 已 false；若补拉期间又被 force，
          // 该调用同样被 loading 拦截并再记账，机制自然收敛、无递归死循环。
          // 内联 await：首个调用方（如广播触发的 invalidate）拿到补拉完成后的最终状态
          this.pendingForce = false
          await this.ensureSpecs(true)
        }
      }
    },
    /** 强制失效重拉（事件广播 / 消费方主动失效入口） */
    async invalidate(): Promise<void> {
      await this.ensureSpecs(true)
    },
    getSpec(type: string): ComponentSpec | undefined {
      return this.specMap.get(type)
    },
  },
})

/** 失效广播订阅：组件发布 / 回滚 / 下线 → 强制重拉规格（§2.3 缓存失效链路）。
 *  事件发射方（组件管理操作链路）由后续任务接线；本函数只负责订阅侧，
 *  供应用入口（main.ts 安装 pinia 之后）一次性调用。
 *  busWired 幂等保护：HMR / 重复调用时不重复入队（bus.on 无自动去重）。 */
let busWired = false

export function setupComponentStoreBus(): void {
  if (busWired) return
  busWired = true
  const refresh = () => { void useComponentStore().invalidate() }
  bus.on('component:published', refresh)
  bus.on('component:rolled-back', refresh)
  bus.on('component:offline', refresh)
}
