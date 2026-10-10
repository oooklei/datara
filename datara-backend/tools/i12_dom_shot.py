"""
i12 三证之③ —— Playwright DOM 取证（沙箱侧跑，直连 ssh 反向隧道 18090 -> 1.9 nginx:8090）

诚实纪律：
- 截图目标 = http://127.0.0.1:18090 （沙箱本地端口，经已实证的 ssh 反向隧道指向 192.168.1.9:8090 真实 nginx/web 容器）
- 此路径在多个独立探针中均返回 200 + Server: nginx/1.27.5（1.9 实机栈），非本地伪造页面
- 输出：DOM 断言 JSON + 全页截图 PNG，落盘本机
"""

import json
import os
import sys

URL = "http://127.0.0.1:18090/"
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i12_dom_proof.png")
DOM_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i12_dom_assert.json")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(json.dumps({"ok": False, "step": "import", "err": str(e)}, ensure_ascii=False))
        return 1
    res = {"ok": False, "url": URL}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            resp = page.goto(URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(3000)
            res["ok"] = True
            res["http_status"] = resp.status if resp else None
            res["server"] = resp.headers.get("server") if resp else None
            res["title"] = page.title()
            res["final_url"] = page.url
            # DOM 结构断言
            res["h1"] = page.locator("h1").first.text_content(timeout=3000) if page.locator("h1").count() else None
            res["nav_links"] = page.locator("nav a").count()
            res["nav_labels"] = (
                [t.strip() for t in page.locator("nav a").all_text_contents()][:10]
                if page.locator("nav").count()
                else []
            )
            res["tables"] = page.locator("table").count()
            body = page.locator("body").inner_text(timeout=5000)
            res["body_snippet"] = body[:500]
            # 截图
            page.screenshot(path=SHOT, full_page=True)
            res["shot"] = SHOT
            res["shot_bytes"] = os.path.getsize(SHOT)
            browser.close()
    except Exception as e:
        res["err"] = repr(e)
    with open(DOM_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") and res.get("shot_bytes") else 1


if __name__ == "__main__":
    sys.exit(main())
