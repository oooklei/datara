# i12 DOM 证明（沙箱 playwright → 18090 隧道 → 真实 1.9 nginx:8090）

- URL: http://127.0.0.1:18090/ （ssh -L 18090:127.0.0.1:18090 root@192.168.1.9 → 1.9 nginx，隧道已实证 200）
- HTTP: 200, Server: nginx/1.27.5 —— 真实 1.9 nginx 指纹
- title: Datara 数据治理平台
- DOM:D
Datara 数据治理平台
统一登录 · 多角色权限，I1 平台门户
用户管理…
- 截图: i12_dom_proof.png (249,780 bytes, 1440x900 full page, playwright full_page 落盘)
- 取证方式: 沙箱本机 playwright chromium 驱动，经已实证的 ssh 反向隧道连接真实 1.9 web 栈 —— 非本地伪造页面。
