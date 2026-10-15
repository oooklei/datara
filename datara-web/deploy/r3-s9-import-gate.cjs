'use strict';

// R3-S9 导入闸 PASS 判定（单一事实源）：runner 与 pytest 假响应回归测试共用。
// PASS 必须同时满足：
//   1. 导入响应为已接受的 2xx 状态；
//   2. 页面导入状态为终态成功文案（导入与只读复核通过）；
//   3. 页面运行时状态为终态 complete。
// 注意："导入事务已完成"是中间态（只读复核尚未执行，Codex 裁定），不得作为 PASS 依据；
// 批次字样/中间完成/复核计数异常/部分完成/超时/非 2xx 一律 fail-closed。
const IMPORT_SUCCESS_PATTERN = /导入与只读复核通过/;

function importGateVerdict(importResponse, importStatusText, runtimeState) {
  const status =
    importResponse && typeof importResponse.status === 'number' ? importResponse.status : null;
  const importAccepted = status !== null && status >= 200 && status < 300;
  const importSucceededInUi = IMPORT_SUCCESS_PATTERN.test(importStatusText || '');
  const runtimeComplete = runtimeState === 'complete';
  return {
    status,
    importAccepted,
    importSucceededInUi,
    runtimeComplete,
    pass: importAccepted && importSucceededInUi && runtimeComplete,
  };
}

module.exports = { IMPORT_SUCCESS_PATTERN, importGateVerdict };
