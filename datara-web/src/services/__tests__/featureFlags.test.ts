/**
 * §0.3 灰度开关登记表（featureFlags）单元测试。
 * 关键钉死：默认值 sseSource='polling' / undoCommandStack=false（默认路径不得回归）；
 * 无存储环境（node / 隐私模式）回落默认；脏数据（非法 JSON / 非法枚举 / 非布尔）回落默认；
 * setFlags 合并写入往返 + 响应式版本号自增（供 computed 订阅翻转）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getFlags, getSseSource, isUndoCommandStackOn, setFlags, flagsVersion } from '../featureFlags'

afterEach(() => vi.unstubAllGlobals())

describe('§0.3 datara.flags 灰度开关', () => {
  it('默认值钉死：无 localStorage 环境（node / 隐私模式）一律回落默认', () => {
    expect(getFlags()).toEqual({ sseSource: 'polling', undoCommandStack: false })
    expect(getSseSource()).toBe('polling')
    expect(isUndoCommandStackOn()).toBe(false)
  })

  it('正常读取既有配置（sseSource=pubsub / undoCommandStack=true）', () => {
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => (k === 'datara.flags' ? '{"sseSource":"pubsub","undoCommandStack":true}' : null),
      setItem: () => undefined,
    })
    expect(getFlags()).toEqual({ sseSource: 'pubsub', undoCommandStack: true })
  })

  it('脏数据回落默认：非法 JSON / 非法枚举 / 非布尔一律取默认', () => {
    const raws = ['not-json', '{"sseSource":"bogus"}', '{"undoCommandStack":"yes"}', 'null', '']
    for (const raw of raws) {
      vi.stubGlobal('localStorage', {
        getItem: (k: string) => (k === 'datara.flags' ? raw : null),
        setItem: () => undefined,
      })
      expect(getFlags()).toEqual({ sseSource: 'polling', undoCommandStack: false })
    }
  })

  it('setFlags 合并写入往返 + 响应式版本号自增', () => {
    const store = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v) },
    })
    const v0 = flagsVersion()
    setFlags({ sseSource: 'pubsub' })
    expect(flagsVersion()).toBeGreaterThan(v0)
    expect(getSseSource()).toBe('pubsub')
    expect(isUndoCommandStackOn()).toBe(false) // 合并写入不影响其他项
    setFlags({ undoCommandStack: true })
    expect(getFlags()).toEqual({ sseSource: 'pubsub', undoCommandStack: true })
    expect(JSON.parse(store.get('datara.flags')!)).toEqual({ sseSource: 'pubsub', undoCommandStack: true })
  })
})
