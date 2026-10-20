/**
 * FE-02 横幅一致性断言（C22 续单 2026-10-19）。
 *
 * 断言面：每个验证页 el-alert 横幅文案与对应契约文件的接线状态一致。
 * - RED 契约（源码含活哨兵 throw new Error(<NOT_WIRED_CONST>)）→ 横幅含 "RED 骨架"，不含 "契约已接线"
 * - GREEN 契约 → 横幅含 "契约已接线"，不含 "RED 骨架"
 * - 横幅有且仅用一个状态词（禁三态混用）
 * - el-alert type 与状态映射一致（RED→warning，GREEN→success）
 *
 * 单一事实源：services/rebuild/bannerStatus.ts（detectWiringState + bannerTitleFor + bannerAlertType）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { detectWiringState } from '../bannerStatus'

const REBUILD_DIR = resolve(__dirname, '..')
const VALIDATION_DIR = resolve(__dirname, '../../../views/rebuild/validation')

/** 验证页 → 契约文件映射（10 页一一对应） */
const VIEW_TO_CONTRACT: Record<string, string> = {
  'variable/VariableValidationView.vue': 'variableApi.ts',
  'dependency-form/DependencyFormValidationView.vue': 'dependencyApi.ts',
  'resource-upload/ResourceUploadValidationView.vue': 'resourceApi.ts',
  'sync-form/SyncFormValidationView.vue': 'syncComponentApi.ts',
  'sql-ide-readonly/SqlIdeReadonlyView.vue': 'sqlIdeApi.ts',
  'sql-ide-ddl/SqlIdeDdlView.vue': 'sqlIdeDdlApi.ts',
  'schedule/ScheduleValidationView.vue': 'scheduleApi.ts',
  'metrics/MetricsValidationView.vue': 'metricsApi.ts',
  'stream/StreamValidationView.vue': 'streamApi.ts',
  'ai-assistant/AiAssistantValidationView.vue': 'aiToolsApi.ts',
}

function readSourceFile(relativePath: string): string {
  return readFileSync(resolve(REBUILD_DIR, relativePath), 'utf8')
}

function readViewSource(relativePath: string): string {
  return readFileSync(resolve(VALIDATION_DIR, relativePath), 'utf8')
}

describe('FE-02 banner wiring consistency', () => {
  it('detectWiringState correctly classifies all 10 rebuild contracts', () => {
    const expected: Record<string, 'RED' | 'GREEN'> = {
      'variableApi.ts': 'GREEN',
      'dependencyApi.ts': 'GREEN',
      'resourceApi.ts': 'GREEN',
      'syncComponentApi.ts': 'GREEN',
      'sqlIdeApi.ts': 'GREEN',
      'sqlIdeDdlApi.ts': 'RED',
      'scheduleApi.ts': 'RED',
      'metricsApi.ts': 'GREEN',
      'streamApi.ts': 'GREEN',
      'aiToolsApi.ts': 'GREEN',
    }
    for (const [contractFile, expectedState] of Object.entries(expected)) {
      const source = readSourceFile(contractFile)
      expect(detectWiringState(source), contractFile).toBe(expectedState)
    }
  })

  it('every validation page banner matches its contract wiring state', () => {
    for (const [viewPath, contractFile] of Object.entries(VIEW_TO_CONTRACT)) {
      const vueSource = readViewSource(viewPath)
      const contractSource = readSourceFile(contractFile)
      const state = detectWiringState(contractSource)

      // 提取 bannerTitleFor() 调用的 code 和 state 参数
      const bannerCallMatch = vueSource.match(
        /bannerTitleFor\(\s*\{[^}]*code:\s*'([^']+)'[^}]*\}\s*,\s*'(\w+)'\s*,?\s*\)/,
      )
      expect(bannerCallMatch, `${viewPath} bannerTitleFor() call`).toBeTruthy()
      const code = bannerCallMatch![1]
      const bannerState = bannerCallMatch![2]

      // 检查 banner state 与契约接线状态一致
      expect(bannerState, `${viewPath} banner state`).toBe(state)

      // 检查 code 与契约代号一致（契约文件中的 R*_/I*_ 前缀）
      const contractCodeMatch = contractSource.match(/R[0-9]+[A-Z]_|I[0-9]+[A-Z]_/)
      const viewCodeNormalized = code.toLowerCase().replace('-', '')
      const contractCode = (contractCodeMatch?.[0] ?? '').replace(/_$/, '').toLowerCase()
      expect(viewCodeNormalized, `${viewPath} code ${code} matches contract ${contractCode}`).toContain(
        contractCode.replace('5a', '5a').replace('5b', '5b'),
      )
    }
  })

  it('no banner mixes multiple wiring states (no 三态混用)', () => {
    for (const [viewPath] of Object.entries(VIEW_TO_CONTRACT)) {
      const vueSource = readViewSource(viewPath)
      // 找到横幅 el-alert（data-testid 含 "banner"）
      const bannerAlertMatch = vueSource.match(/<el-alert[^>]*data-testid="[^"]*banner[^"]*"[^>]*>/)
      expect(bannerAlertMatch, `${viewPath} banner el-alert should exist`).toBeTruthy()
      const bannerTag = bannerAlertMatch![0]

      // 横幅 title 应为动态绑定（:title="bannerTitle"），不是静态字符串
      const dynamicTitleMatch = bannerTag.match(/:title="bannerTitle"/)
      expect(dynamicTitleMatch, `${viewPath} banner title should be dynamic`).toBeTruthy()

      // bannerTitleFor() 的 state 参数应为 RED 或 GREEN，不是 待评审
      const bannerCallMatch = vueSource.match(/bannerTitleFor\(\s*\{[^}]*\}\s*,\s*'(\w+)'\s*,?\s*\)/)
      expect(bannerCallMatch, `${viewPath} bannerTitleFor() call`).toBeTruthy()
      const bannerState = bannerCallMatch![1]
      expect(
        bannerState,
        `${viewPath} banner state must be RED or GREEN, not 待评审`,
      ).not.toBe('待评审')
    }
  })

  it('el-alert type matches wiring state (RED→warning, GREEN→success)', () => {
    for (const [viewPath, contractFile] of Object.entries(VIEW_TO_CONTRACT)) {
      const vueSource = readViewSource(viewPath)
      const contractSource = readSourceFile(contractFile)
      const state = detectWiringState(contractSource)

      // 找到横幅 el-alert（data-testid 含 "banner"），排除状态栏
      const bannerAlertMatch = vueSource.match(/<el-alert[^>]*data-testid="[^"]*banner[^"]*"[^>]*>/)
      expect(bannerAlertMatch, `${viewPath} banner el-alert should exist`).toBeTruthy()
      const bannerTag = bannerAlertMatch![0]

      // 动态绑定 :type="bannerType" → 检查 bannerAlertType(...) 调用
      if (/:type="bannerType"/.test(bannerTag)) {
        const bannerTypeMatch = vueSource.match(/const bannerType = bannerAlertType\('(\w+)'\)/)
        expect(bannerTypeMatch, `${viewPath} bannerType variable should exist`).toBeTruthy()
        const alertState = bannerTypeMatch![1]
        if (state === 'RED') {
          expect(alertState, `${viewPath} RED bannerType`).toBe('RED')
        } else {
          expect(alertState, `${viewPath} GREEN bannerType`).toBe('GREEN')
        }
      } else {
        // 静态绑定 type="warning|success" → 直接比较
        const staticTypeMatch = bannerTag.match(/type="(warning|success)"/)
        expect(staticTypeMatch, `${viewPath} static banner type`).toBeTruthy()
        const vueType = staticTypeMatch![1]
        if (state === 'RED') {
          expect(vueType, `${viewPath} RED banner type`).toBe('warning')
        } else {
          expect(vueType, `${viewPath} GREEN banner type`).toBe('success')
        }
      }
    }
  })

  it('every validation page imports bannerStatus vocabulary (FE-01 单一事实源)', () => {
    for (const [viewPath] of Object.entries(VIEW_TO_CONTRACT)) {
      const vueSource = readViewSource(viewPath)
      expect(
        vueSource,
        `${viewPath} should import bannerStatus vocabulary`,
      ).toContain('bannerStatus')
    }
  })
})
