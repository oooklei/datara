/**
 * dbx 变量桥契约（Step 11）：datara 宿主页 → dbx iframe 的 postMessage 载荷与安全口径。
 *
 * 断言面（4 项）：
 *  1. 消息协议常量稳定（消息类型 + dbx 宿主 origin）；
 *  2. 敏感变量在下发载荷中已脱敏，非敏感变量保留现时值；
 *  3. iframe 未挂载时下发返回 false（不抛错，由 bridge-ready 补发兜底）；
 *  4. iframe 就绪时向 contentWindow 按协议载荷 + 目标 origin 下发。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DATARA_VARIABLES_MESSAGE,
  DBX_IFRAME_ORIGIN,
  buildVariableEntries,
  maskSensitiveValue,
  sendVariablesToDbx,
} from '../../services/rebuild/dbxVariableBridge'
import type { VariableCompletionItem } from '../../services/rebuild/variableApi'

const items: VariableCompletionItem[] = [
  { scope: 'project', name: 'db_name', valueType: 'string', currentValue: 'analytics' },
  { scope: 'env', name: 'db_password', valueType: 'string', currentValue: 's3cr3t', sensitive: true },
  { scope: 'global', name: 'batch_date', valueType: 'date', currentValue: null, unavailableReason: '未设置' },
]

afterEach(() => {
  vi.restoreAllMocks()
})

describe('dbx variable bridge contract', () => {
  it('消息协议常量稳定：datara:variables 下发、目标 origin 与宿主同源', () => {
    expect(DATARA_VARIABLES_MESSAGE).toBe('datara:variables')
    expect(DBX_IFRAME_ORIGIN).toBe(window.location.origin)
  })

  it('敏感变量在下发载荷中脱敏为掩码，非敏感变量保留现时值', () => {
    expect(maskSensitiveValue()).toBe('***')

    const entries = buildVariableEntries(items)

    expect(entries.map((e) => e.value)).toEqual(['analytics', '***', null])
    expect(entries.find((e) => e.name === 'db_password')).toMatchObject({
      scope: 'env',
      valueType: 'string',
      sensitive: true,
      value: '***',
    })
    expect(entries.find((e) => e.name === 'batch_date')).toMatchObject({
      value: null,
      unavailableReason: '未设置',
      sensitive: false,
    })
  })

  it('iframe 未挂载时下发返回 false（不抛错，等待 bridge-ready 补发）', () => {
    expect(document.querySelector('#dbx-ide-frame')).toBeNull()
    expect(sendVariablesToDbx(buildVariableEntries(items))).toBe(false)
  })

  it('iframe 就绪时按协议载荷与目标 origin 向 contentWindow 下发', () => {
    const postMessage = vi.fn()
    vi.spyOn(document, 'querySelector').mockReturnValue({
      contentWindow: { postMessage },
    } as unknown as HTMLIFrameElement)

    const entries = buildVariableEntries(items)
    expect(sendVariablesToDbx(entries)).toBe(true)
    expect(postMessage).toHaveBeenCalledTimes(1)
    expect(postMessage).toHaveBeenCalledWith(
      { type: DATARA_VARIABLES_MESSAGE, entries },
      DBX_IFRAME_ORIGIN,
    )
  })
})
