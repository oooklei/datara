# 14-01 — `t_lineage_edge` Shape A 正式落地（R-46）

## 裁定与实现

- 裁定锚：`s301-gov-ruling-registry-dispatch-20261021` / R-46。
- Shape A 主体已在 17.2-21 前置实现并进入 HEAD：`rebuild/model/models.py::LineageEdgeRecord` 逐列承载旧侧 `common.models.LineageEdge`，并纳入 `MODEL_TABLES`。
- 本票补齐独立回归门 `test_model_lineage_edge_shape_a.py`，锁定 15 列类型、nullable、主键、自增、Python/server 默认值语义、三索引、六列 `uk_lineage` 幂等键，以及 rebuild 装配中恰有一个 `t_lineage_edge`。
- 同名表未来冲突仍按 R-46 交由监督线裁定唯一归属域；本票未引入第二定义。

## 验证

1. `python -m pytest -q tests/rebuild/test_model_lineage_edge_shape_a.py`
   - `2 passed in 0.36s`
2. `python -m pytest -q tests/rebuild/test_model_lineage_api.py`
   - `27 passed in 51.93s`
3. `git diff --check -- datara-backend/tests/rebuild/test_model_lineage_edge_shape_a.py`
   - PASS（无输出）

首轮结构测试把等价时间默认函数名 `_now`/`now` 误判为漂移；比较器已修正为 callable 语义，随后全绿。

## SHA256

- `datara-backend/rebuild/model/models.py`: `8f73e523bbd869e973b367cb7dd634d221ecdcc2fea1c103c343019a1e1b398e`
- `datara-backend/tests/rebuild/test_model_lineage_edge_shape_a.py`: `946367df158e47940f74137ff0721e9a7eb4f60856679b5335760a5d8b26b12b`
- `datara-backend/tests/rebuild/test_model_lineage_api.py`: `fd1ea1a46ee0306785d01ac0fffaba8deb221cb3ed7f29d5ab84a46d089389d4`

## 文件清单

- `datara-backend/tests/rebuild/test_model_lineage_edge_shape_a.py`（本票新增）
- `docs/increments/evidence/INC14/2026-10-21-14-01-t_lineage_edge-Shape-A-Codex.md`（本证据）
- `datara-backend/rebuild/model/models.py`（既有 Shape A 主体，未重复修改）

提交号：无，工作区改动，待监督线代提交。
