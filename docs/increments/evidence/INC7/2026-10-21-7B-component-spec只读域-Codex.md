# 7B component spec 独立只读域实施证据

> 日期：2026-10-21  
> 前置：7A 契约评审通过；R-37、R-38、R-39 已生效

## 交付

- 新建 `rebuild/component_spec/` 独立域，通过只读 service/adapter 读取既有 `Component` 与 `ComponentVersion` 治理表。
- 装配 `GET /api/v1/rebuild/components/spec`，认证复用 `TokenService` 与 active token 检查。
- 仅返回主表与精确 published version 均为 published 的记录，并按 `Component.id` 稳定排序。
- 200 返回裸 `{"items":[...]}`；ETag 为实际响应字节的完整 SHA-256 强验证器。
- `If-None-Match` 命中返回 304、空 body、同一 ETag。
- 损坏 JSON 快速失败为标准错误信封，不伪造 200 空清单；匿名或撤销 token 在读库前拒绝。
- 未转挂旧 router，未把 `dag_catalog.json` 用作运行时第二真源。

## 实跑

```text
python -m pytest tests/rebuild/test_component_spec_api.py -q
3 passed in 3.20s

python -m pytest tests/rebuild/test_component_spec_api.py tests/rebuild/test_identity_api.py -q
20 passed in 15.66s
```

测试覆盖：双 published 精确 join、稳定响应字节、完整强 ETag、304 空 body、坏数据失败、认证拒绝和身份域装配回归。

## 文件

- `datara-backend/rebuild/component_spec/__init__.py`
- `datara-backend/rebuild/component_spec/api.py`
- `datara-backend/rebuild/component_spec/service.py`
- `datara-backend/rebuild/api/app.py`
- `datara-backend/tests/rebuild/test_component_spec_api.py`

## 边界

- 7D 前端缓存与 degraded 消费尚未实施，因此 `CONTRACT_REGISTRY` 例外项仍应保持 RED。
- 未提交、未 push、未修改 `.git`、未调用 `aoci_*`。
