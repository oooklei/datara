# 7C spec 发布闸门强化核验

> 日期：2026-10-21  
> 前置：7A 契约冻结、7B 只读域完成

## 结论

现有 `api/component_design.py` 发布路径已经具备本票要求的强闸门，核验通过，无需重复实现第二套发布器：

- 严格 JSON round-trip，拒绝 NaN、Infinity、不可序列化值和函数/代码片段残留；
- `fields` 与八段底稿 `form.params` 双源同口径校验；
- `uiType`、`pick`、`dropPolicy` 键及枚举采用封闭白名单；
- type 使用数据库全局唯一约束及目录同名保守拒绝，避免声明歧义；
- `dag-engine` 必须绑定真实 dispatch registry executor；`demo-only` 禁发布；
- `canvas-device`、`page` 强制不可执行，`runtime-only` 强制 `paletteVisible=false`；
- `prefillFromUpstream` 与 page bindings 资源引用逐项验证；
- 发布端点无 force/豁免开关，任一 gate 失败返回全部违规，不存在“可声明但不可执行”的静默放行。

发布闸门复用 `components.catalog` 的单一执行器注册表，未复制 executor 清单，因此 worker 路由与执行实现不会产生第二真源漂移。

## 实跑

```text
python -m pytest tests/test_component_design.py tests/test_component_catalog.py -q
151 passed in 15.16s
```

覆盖纯数据、代码片段、白名单、占位符、page DSL、executor 注册表、runtimeOnly 与目录一致性正负用例。

## 文件与边界

- 核验代码：`datara-backend/api/component_design.py`
- 核验测试：`datara-backend/tests/test_component_design.py`、`datara-backend/tests/test_component_catalog.py`
- 本票仅新增本证据文件；生产代码无需修改。
- 未提交、未 push、未修改 `.git`、未调用 `aoci_*`。
