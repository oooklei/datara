from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


PAGE = Path(__file__).parents[1] / "public" / "rebuild-validation-r3-s9.html"
RUNNER = Path(__file__).parent / "r3-s9-i18-preview.cjs"
LAUNCHER = Path(__file__).parent / "run-r3-s9-i18-preview.ps1"


class PageControls(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.inputs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if element_id := values.get("id"):
            self.ids.append(element_id)
        if tag == "input":
            self.inputs.append((values.get("type", "text"), values.get("id", "")))


def test_i18_preview_page_has_prepopulated_project_and_operable_preview_controls():
    html = PAGE.read_text(encoding="utf-8")
    controls = PageControls()
    controls.feed(html)

    assert {
        "projectSelect",
        "runDryRun",
        "reloadProjects",
        "planRows",
        "issueList",
        "importOrder",
        "importStatus",
        "importConfirmPhrase",
        "runI18Import",
    } <= set(
        controls.ids
    )
    assert 'data-testid="run-dry-run"' in html
    assert "已载入" in html and "result.list[0]?.id" in html
    assert "请先选择目标项目并执行只读预检" in html
    assert "不写入任何目标业务表" in html
    assert len(controls.ids) == len(set(controls.ids))


def test_i18_preview_page_uses_short_lived_injected_token_without_login_or_key_storage():
    html = PAGE.read_text(encoding="utf-8").lower()
    controls = PageControls()

    controls.feed(html)
    assert "__datara_test_token__" in html
    assert "x-backend-validation-key" not in html
    assert "rebuild_validation_key" not in html
    assert "localstorage" not in html
    assert "sessionstorage" not in html
    assert not any(name in {"username", "password", "login"} for _, name in controls.inputs)
    assert not any(name == "importConfirmPhrase" and kind == "password" for kind, name in controls.inputs)


def test_i18_preview_page_calls_actual_read_only_dry_run_contract_and_renders_response_fields():
    html = PAGE.read_text(encoding="utf-8")

    assert "/api/v1/rebuild/projects" in html
    assert "/legacy/i18/dry-run" in html
    for contract_field in (
        "source.counts",
        "source.digest",
        "target.identity_count",
        "plan.counts",
        "plan.entries",
        "plan.import_order",
        "plan.issues",
        "plan.ready_to_import",
    ):
        assert contract_field in html


def test_i18_runner_uses_protected_runtime_key_and_real_page_controls():
    runner = RUNNER.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert "http://192.168.1.9:18091" in runner and "rebuild-validation-r3-s9.html" in runner
    assert "DATARA_REBUILD_VALIDATION_KEY" in runner and "validation-token" in runner
    assert "addInitScript" in runner and "__DATARA_TEST_TOKEN__" in runner
    assert "getByTestId('run-dry-run').click()" in runner
    assert "snapshot_digests" in runner and "sourceDigest" in runner and "targetDigest" in runner
    assert "approved-project-3" in runner
    assert "importConfirmPhrase" in runner and "runI18Import" in runner
    assert "run-i18-import-confirmation-ready" in runner
    assert "getByTestId('run-i18-import').click()" not in runner
    assert "writeFile(reportPath" in runner and "screenshot" in runner
    assert "REBUILD_VALIDATION_KEY" in launcher
    assert "Remove-Item Env:DATARA_REBUILD_VALIDATION_KEY" in launcher
    assert "localStorage" not in runner and "sessionStorage" not in runner


def test_i18_preview_page_generates_idempotency_key_in_non_secure_context():
    """缺口 #1：crypto.randomUUID 仅 secure context 可用；页面必须带回退，禁止无条件调用。"""
    html = PAGE.read_text(encoding="utf-8")

    assert "generateIdempotencyKey" in html
    # crypto.randomUUID() 只允许出现在类型守卫后的 return 处（1 次），禁止任何无条件调用
    assert html.count("crypto.randomUUID()") == 1
    assert "typeof crypto?.randomUUID === 'function'" in html
    assert "getRandomValues" in html
    assert "(bytes[6] & 0x0f) | 0x40" in html and "(bytes[8] & 0x3f) | 0x80" in html
    assert "无安全随机源" in html


def test_i18_preview_page_plan_table_has_no_misleading_target_entity_column():
    """缺口 #3：后端 entries 契约无 target 实体字段，列须删除而非误渲染 source_table。"""
    html = PAGE.read_text(encoding="utf-8")

    assert "<th>目标实体</th>" not in html
    assert "<th>来源表</th><th>来源主键</th><th>计划</th><th>说明</th>" in html
    assert 'colspan="5"' not in html and 'colspan="4"' in html
    rendered = html.split("planRows').innerHTML=entries.length")[1]
    assert "<td>${escapeHtml(entry.source_table)}</td><td>${escapeHtml(entry.source_id)}</td><td><span" in rendered


def test_i18_preview_page_preserves_4097_partial_completion_payload():
    """缺口 #4：4097 部分完成响应的 batch_id/status 须保存到 error.data 并在导入状态展示。"""
    html = PAGE.read_text(encoding="utf-8")

    assert "error.data=payload.data??null" in html
    assert "error&&error.data&&error.data.batch_id" in html
    assert "导入部分完成：批次" in html and "partial.status" in html and "partial.imported_count" in html


def test_i18_preview_page_pill_covers_all_dispositions():
    """缺口 #7：skipped/unchanged 徽章须有专属配色。"""
    html = PAGE.read_text(encoding="utf-8")

    assert ".pill.skipped{" in html and ".pill.unchanged{" in html


def test_i18_preview_page_mapping_details_survive_disposition_reason():
    """缺口 #6：映射明细与 disposition_reason 拼接展示，不得被 fallback 链遮蔽。"""
    html = PAGE.read_text(encoding="utf-8")

    assert "[entry.disposition_reason,notes,entry.fingerprint].filter(Boolean).join" in html
    assert "entry.disposition_reason||notes||entry.fingerprint" not in html


def test_i18_preview_page_reveals_idempotency_key_and_states_refresh_risk():
    """缺口 #5：幂等键在导入状态可见可审计；锁定文案如实陈述刷新后会生成新键（无存储契约不变）。"""
    html = PAGE.read_text(encoding="utf-8").lower()

    assert "幂等键 ${state.idempotencykey}" in html
    assert "刷新页面会生成新的幂等键" in html
    assert "localstorage" not in html and "sessionstorage" not in html and "document.cookie" not in html


def test_i18_preview_page_token_surface_stays_injection_only():
    """缺口 #2 合同：token 只读 window.__DATARA_TEST_TOKEN__ 注入面，不落 DOM 属性/存储/日志。"""
    html = PAGE.read_text(encoding="utf-8")

    assert "window.__DATARA_TEST_TOKEN__ || ''" in html
    token_reads = html.count("__DATARA_TEST_TOKEN__")
    assert token_reads == 1
    assert "console." not in html
    assert "Authorization:`Bearer ${token}`" in html


ADMIN_LAUNCHER = Path(__file__).parent / "run-r3-s9-i18-admin-headed.ps1"


def test_i18_headed_admin_launcher_reads_token_from_console_and_clears_it():
    """缺口 #2 合同：headed launcher 从本机安全输入读 token（不回显）、缓冲归零、退出清环境、不落盘。"""
    script = ADMIN_LAUNCHER.read_text(encoding="utf-8")

    assert "Read-Host" in script and "-AsSecureString" in script
    assert "SecureStringToBSTR" in script and "ZeroBSTR" in script
    assert "DATARA_REBUILD_ADMIN_TOKEN" in script
    assert "Remove-Item Env:DATARA_REBUILD_ADMIN_TOKEN" in script
    assert "Out-File" not in script and "Set-Content" not in script and "Add-Content" not in script


def test_i18_runner_admin_mode_keeps_import_under_human_control():
    """缺口 #2 合同：admin-headed 模式 headed 打开、token 仅经 init script 注入内存、导入仍由人工点击。"""
    runner = RUNNER.read_text(encoding="utf-8")

    assert "DATARA_REBUILD_ADMIN_TOKEN" in runner
    assert "admin-headed-manual-injection" in runner
    assert "headless: adminHeaded ? false : true" in runner
    # 双模式互斥：不得同时设置 validation key 与 admin token
    assert "Set exactly one of DATARA_REBUILD_VALIDATION_KEY / DATARA_REBUILD_ADMIN_TOKEN" in runner
    # runner 任何模式都不得代输确认语或点击导入按钮
    assert "getByTestId('run-i18-import')" not in runner
    assert "importConfirmPhrase').fill(" not in runner and "keyboard" not in runner
    assert "waiting-for-human-confirmation-and-click" in runner
    # token 不进证据：报告/检查输出无 token 值字段
    assert "admin_token:" not in runner and "token:" not in runner.replace("auth_token", "")
