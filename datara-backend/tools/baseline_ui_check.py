"""
基线化流水线 UI 实测（2026-09-29 查漏补缺）—— Playwright 无头浏览器
目标 = http://localhost:5175 （本机 vite dev，VITE_API_MODE=mock，mock 模式免登录）
路由口径（与 routes.ts 对齐）：
  1. /#/meta/baseline 基线化工作台（三区/进度表/状态徽标）+ 选中「端点选择」行 → 八段编辑器页签
  2. /#/meta/components/design/ssh 组件设计器（M1 四 Tab：基本信息/端口/表单字段/dropPolicy）
  3. /#/dag?doc=wf_order_daily 画布（?doc= 直达载入 seed 工作流 → palette 分组与组件项）
输出：baseline_ui_assert.json + 3 张截图（本目录）
"""
import json
import os

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5175"
OUT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    res: dict = {"ok": True, "pages": {}, "console_errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 950})
        page.on("console", lambda m: res["console_errors"].append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: res["console_errors"].append(f"pageerror: {e}"))
        res["failed_requests"] = []
        page.on("response", lambda r: res["failed_requests"].append(f"{r.status} {r.url}") if r.status >= 400 else None)

        # ---------- 1. 基线化工作台 ----------
        try:
            page.goto(f"{BASE}/#/meta/baseline", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            body = page.locator("body").inner_text(timeout=8000)
            pg = {"final_url": page.url}
            for key, kw in {
                "分组_同步类": "同步类", "分组_ETL计算类": "ETL / 计算类",
                "状态_待认可": "待认可", "状态_设计中": "设计中", "状态_未开始": "未开始",
                "组件_endpoint_select": "endpoint_select", "组件_sql": "sql",
                "证据区_体检": "体检",
            }.items():
                pg[key] = kw in body
            pg["body_chars"] = len(body)
            pg["crow_rows"] = page.locator(".crow").count()
            # 选中「端点选择」行（div.crow）→ 设计区载入八段编辑器
            try:
                row = page.locator(".crow", has_text="endpoint_select").first
                row.click(timeout=8000)
                page.wait_for_timeout(2000)
                body2 = page.locator("body").inner_text(timeout=8000)
                for seg in ["输入", "输出", "参数", "条件", "约束", "排除", "引用变量", "输出变量"]:
                    pg[f"八段_{seg}"] = seg in body2
                pg["选中后_体检"] = "体检" in body2
            except Exception as e:  # noqa: BLE001
                pg["八段交互错误"] = str(e)[:200]
            page.screenshot(path=os.path.join(OUT, "ui_baseline_workbench.png"), full_page=True)
            res["pages"]["baseline_workbench"] = pg
        except Exception as e:  # noqa: BLE001
            res["pages"]["baseline_workbench"] = {"error": str(e)}
            res["ok"] = False

        # ---------- 2. 组件设计器（M1 四 Tab） ----------
        try:
            page.goto(f"{BASE}/#/meta/components/design/ssh", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            body = page.locator("body").inner_text(timeout=8000)
            pg = {"final_url": page.url}
            for tab_name in ["基本信息", "端口", "表单字段", "dropPolicy"]:
                pg[f"设计器Tab_{tab_name}"] = tab_name in body
            pg["实时预览"] = "实时预览" in body
            pg["版本区"] = ("版本" in body)
            pg["body_chars"] = len(body)
            page.screenshot(path=os.path.join(OUT, "ui_component_designer.png"), full_page=True)
            res["pages"]["component_designer_ssh"] = pg
        except Exception as e:  # noqa: BLE001
            res["pages"]["component_designer_ssh"] = {"error": str(e)}
            res["ok"] = False

        # ---------- 3. 画布 palette（?doc= 直达载入 seed 工作流） ----------
        try:
            page.goto(f"{BASE}/#/dag?tab=edit&type=wf&doc=wf_order_daily",
                      wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            body = page.locator("body").inner_text(timeout=8000)
            pg = {"final_url": page.url}
            for grp in ["数据计算", "通用", "逻辑控制", "数据同步", "流处理", "变量", "运维", "模板"]:
                pg[f"palette_{grp}"] = grp in body
            for comp in ["SQL", "通知", "开始", "源表基准编排", "流输入", "变量组件", "冒烟", "示例管道模板"]:
                pg[f"组件_{comp}"] = comp in body
            pg["body_chars"] = len(body)
            page.screenshot(path=os.path.join(OUT, "ui_dag_palette.png"), full_page=True)
            res["pages"]["dag_canvas"] = pg
        except Exception as e:  # noqa: BLE001
            res["pages"]["dag_canvas"] = {"error": str(e)}
            res["ok"] = False

        browser.close()

    # 断言汇总：关键项全过才 ok（console 错误单列不计入 ok，但 404/资源类噪音需人工看）
    wb = res["pages"].get("baseline_workbench", {})
    ds = res["pages"].get("component_designer_ssh", {})
    dag = res["pages"].get("dag_canvas", {})
    checks = [
        wb.get("状态_待认可"),
        wb.get("状态_设计中"),
        wb.get("八段_参数"),
        wb.get("八段_引用变量"),
        wb.get("八段_输出变量"),
        ds.get("设计器Tab_表单字段"),
        dag.get("palette_数据同步"),
        dag.get("palette_流处理"),
    ]
    res["key_checks_passed"] = sum(1 for c in checks if c is True)
    res["key_checks_total"] = len(checks)
    res["ok"] = all(c is True for c in checks)

    out = os.path.join(OUT, "baseline_ui_assert.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": res["ok"], "checks": f"{res['key_checks_passed']}/{res['key_checks_total']}",
                      "console_errors": len(res["console_errors"]),
                      "pages": {k: v.get("error") or f"chars={v.get('body_chars')}" for k, v in res["pages"].items()}},
                     ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
