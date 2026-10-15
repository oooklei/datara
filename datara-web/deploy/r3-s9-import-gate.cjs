'use strict';

// R3-S9 导入闸 PASS 判定（单一事实源）：runner 与 pytest 假响应回归测试共用。
// PASS 必须同时满足：导入响应为已接受的 2xx 状态 + 页面终态为明确成功文案。
// "存在导入响应 + 界面出现批次字样"不足以 PASS（409 部分完成 / 非 2xx / 仅 HTTP 成功 / 仅 UI 成功均 fail-closed）。
const IMPORT_SUCCESS_PATTERN = /导入与只读复核通过|导入事务已完成/;

function importGateVerdict(importResponse, importStatusText) {
  const status =
    importResponse && typeof importResponse.status === 'number' ? importResponse.status : null;
  const importAccepted = status !== null && status >= 200 && status < 300;
  const importSucceededInUi = IMPORT_SUCCESS_PATTERN.test(importStatusText || '');
  return { status, importAccepted, importSucceededInUi, pass: importAccepted && importSucceededInUi };
}

module.exports = { IMPORT_SUCCESS_PATTERN, importGateVerdict };
