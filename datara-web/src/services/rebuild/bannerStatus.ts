/**
 * 横幅状态词表（FE-01 修订：单一事实源，2026-10-19）。
 *
 * 三态词表（每个验证页横幅有且仅用一个状态词，禁三态混用）：
 * - RED：后端契约未接入（原型态），所有 I/O 返回 *_NOT_WIRED。
 * - GREEN：契约已接线，I/O 经统一包络 {code,msg,data}。
 * - 待评审：契约已接线但验证页证据面待独立评审（过渡态，仅验证页退役前使用）。
 *
 * 接线状态判定：契约源码中存在活哨兵 `throw new Error(<NOT_WIRED_CONST>)`（纯常量引用）
 * 为 RED；仅 404 等条件抛错或仅常量声明（如 streamApi）为 GREEN。
 * FE-02 横幅一致性断言（bannerConsistency.contract.test.ts）以本词表为唯一口径。
 */

export type BannerWiringState = 'RED' | 'GREEN' | '待评审'

export interface BannerCopyInput {
  /** 契约代号：R2/R4/R5-A/R5-B/R6/R7/I7/I8/R8-B */
  code: string
  /** rebuild/ 下路径名：variables/dependency/resources/... */
  contractName: string
  /** 冻结方法数（GREEN/待评审态展示） */
  methodCount: number
  /** RED 态哨兵词首（如 R6_SCHEDULER_NOT_WIRED） */
  sentinel?: string
  /** 补充说明（可选，拼接在词表尾部） */
  extra?: string
}

/**
 * 判定契约源码接线状态。
 * RED 特征：方法体内无条件 `throw new Error(<SENTINEL_CONST>)`（括号内仅常量标识符）。
 * GREEN：哨兵仅作常量声明或条件抛错（如 streamApi 404 分支带路径后缀）。
 */
export function detectWiringState(contractSource: string): 'RED' | 'GREEN' {
  return /throw new Error\(\s*[A-Z][A-Z0-9_]*NOT_WIRED\s*\)/.test(contractSource) ? 'RED' : 'GREEN'
}

/** 统一横幅文案（RED/GREEN/待评审三态单一事实源）。 */
export function bannerTitleFor(input: BannerCopyInput, state: BannerWiringState): string {
  if (state === 'RED') {
    const base = `${input.code} RED 骨架（原型态）— rebuild/${input.contractName} 后端契约未接入，所有 I/O 返回 ${input.sentinel ?? 'NOT_WIRED'}`
    return input.extra ? `${base}；${input.extra}` : base
  }
  if (state === '待评审') {
    const base = `${input.code} 契约已接线（rebuild/${input.contractName} P1 冻结词形）— I/O 经统一包络；验证页证据面待独立评审`
    return input.extra ? `${base}；${input.extra}` : base
  }
  const base = `${input.code} 契约已接线（rebuild/${input.contractName} P1 冻结词形）— I/O 经统一包络；${input.methodCount} 方法可调用`
  return input.extra ? `${base}；${input.extra}` : base
}

/** el-alert type 与状态映射（RED→warning，GREEN/待评审→success）。 */
export function bannerAlertType(state: BannerWiringState): 'warning' | 'success' {
  return state === 'RED' ? 'warning' : 'success'
}
