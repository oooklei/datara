import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "docs/increments/evidence/INC7/2026-10-21-7J-组件出处与引用量调查.csv"
OUTPUT = ROOT / "docs/increments/evidence/INC7/2026-10-21-7J-41项权威出处甄别.csv"


with SOURCE.open(encoding="utf-8-sig", newline="") as stream:
    rows = list(csv.DictReader(stream))

targets = [
    row for row in rows
    if row["type"] == "reroute" or row["profile"] in {"etl", "stream", "topo"}
]
assert len(targets) == 41, len(targets)

fields = [
    "ordinal", "type", "code", "label", "profile", "authority_finding",
    "evidence_anchor", "implementation_finding", "triage", "next_action",
    "live_published_state", "static_production_reference_file_count",
]

for row in targets:
    profile = row["profile"]
    if row["type"] == "reroute":
        finding = "无 I0~I11/会议纪要/权威设计编号；存在编辑器便利节点实现"
        anchor = "master/dag.py:16-68; datara-web/src/graph/profiles/dag.ts:277-286"
        implementation = "发布执行前消除并桥接前后边；不是独立运行任务"
        triage = "保留候追认"
        action = "监督线确认其为编辑器结构节点；若追认则补权威登记，禁止直接当无出处运行组件删除"
    elif profile == "etl":
        finding = "当前权威设计明确删除 ETL 工作流和 ETL 算子组件"
        anchor = "权威设计§5A.2 L504-505, §5A.3 L514, 会议决策记录[09-18] L56"
        implementation = "仍在旧 catalog/worker 注册表中，属于被后续用户裁定覆盖的历史实现"
        triage = "建议移出白名单"
        action = "先取现网 published/ref 只读快照；零引用后另立执行票移除 spec/palette/注册并做历史兼容回归"
    elif profile == "stream":
        finding = "仅有旧 Flink 风格 palette；当前正式流组件为 C18/C19/C20/page_board，未逐项背书旧 type"
        anchor = "权威设计§5A.3 L514; 增量13正式流组件设计；原审计 CSV origin_evidence"
        implementation = "旧 type 仍在 catalog/worker 注册；与正式 stream_input/fuse/output 体系并存"
        triage = "建议由正式组件替代"
        action = "建立旧 type→C18/C19/C20 映射；取现网引用后另票迁移历史图并移出旧 spec"
    else:
        finding = "拓扑设备不是 DAG component-spec 产品对象，无逐组件产品出处"
        anchor = "权威设计§5A.3（DAG spec 治理边界）; dag_catalog.json profile=topo/dagRelevant=false/nonExecutable"
        implementation = "仅拓扑画布展示设备，不参与 DAG 执行"
        triage = "移出 DAG 治理范围"
        action = "保留于拓扑专属注册表；从 DAG 白名单/裁定统计中剥离，不按生产任务组件下线"
    row.update(
        authority_finding=finding,
        evidence_anchor=anchor,
        implementation_finding=implementation,
        triage=triage,
        next_action=action,
    )

with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows({field: row[field] for field in fields} for row in targets)

print(f"wrote {len(targets)} rows to {OUTPUT}")
