#!/usr/bin/env python3
"""
export_dag_catalog.py — 从前端 profile 源码生成 dag_catalog.json

解析 datara-web/src/graph/profiles/*.ts 中的 nodeTypes 定义，
生成后端只读组件目录快照（dag_catalog.json）。

用法：
    python scripts/export_dag_catalog.py [--output common/dag_catalog.json]
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# 项目根目录（datara-backend/ 的父目录）
BACKEND_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BACKEND_DIR.parent / "datara-web"
PROFILES_DIR = WEB_DIR / "src" / "graph" / "profiles"

# Profile 文件映射
PROFILE_FILES = {
    "dag": "dag.ts",
    "etl": "etl.ts",
    "stream": "stream.ts",
    "topo": "topo.ts",
    "er": "er.ts",
    "lineage": "lineage.ts",
    "relation": "relation.ts",
}

# 执行模型分类
EXECUTION_MODELS = {
    "dag-engine": "Master 派发点 / Worker executor",
    "passthrough": "直通节点（配置被下游拍平）",
    "template": "模板节点（落图即展开）",
    "nonExecutable": "展示型节点（不产生任务实例）",
    "demo-only": "无执行实现；F56a 演示态（未接 DAG 引擎）",
}

# Worker 执行器类型（与 worker/executors/ 目录对应）
WORKER_TYPES = frozenset({
    "sql", "shell", "python", "ssh", "smoke", "procedure", "http", "file", "sync", "file_sync", "notify",
})

# Master 内联 handler 类型
MASTER_HANDLER_TYPES = frozenset({
    "start", "end", "conditions", "switch", "fork", "join", "merge", "delay", "dependent", "loop",
    "variable", "assert",
    "field_map", "field_map_union", "condition_set", "endpoint_select", "page_board",
    "stream_input", "stream_fuse", "stream_output",
})

# 模板类型
TEMPLATE_TYPES = frozenset({
    "demo_pipeline", "src_base_orch", "tgt_base_orch", "file_sync_orch",
})

# 运行时物化类型
RUNTIME_ONLY_TYPES = frozenset({"sync", "file_sync"})


def find_matching_brace(content: str, start: int) -> int:
    """找到匹配的 } 位置"""
    brace_count = 0
    in_string = False
    string_char = None
    i = start
    while i < len(content):
        c = content[i]
        if in_string:
            if c == '\\':
                i += 2
                continue
            if c == string_char:
                in_string = False
        else:
            if c in ('"', "'", '`'):
                in_string = True
                string_char = c
            elif c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
                if brace_count == 0:
                    return i
        i += 1
    return -1


def parse_ts_value(s: str):
    """解析 TypeScript 值（简化版）"""
    s = s.strip()
    if not s:
        return None

    # 字符串
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.startswith('`') and s.endswith('`'):
        return s[1:-1]

    # 布尔值
    if s == 'true':
        return True
    if s == 'false':
        return False
    if s == 'null':
        return None

    # 数字
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        pass

    # 数组
    if s.startswith('[') and s.endswith(']'):
        inner = s[1:-1].strip()
        if not inner:
            return []
        items = []
        depth = 0
        current = ''
        in_str = False
        str_char = None
        for c in inner:
            if in_str:
                current += c
                if c == '\\':
                    continue
                if c == str_char:
                    in_str = False
            else:
                if c in ('"', "'", '`'):
                    in_str = True
                    str_char = c
                    current += c
                elif c in ('{', '['):
                    depth += 1
                    current += c
                elif c in ('}', ']'):
                    depth -= 1
                    current += c
                elif c == ',' and depth == 0:
                    items.append(parse_ts_value(current))
                    current = ''
                else:
                    current += c
        if current.strip():
            items.append(parse_ts_value(current))
        return items

    # 对象
    if s.startswith('{') and s.endswith('}'):
        return parse_ts_object(s)

    # 函数或其他
    return s


def parse_ts_object(s: str) -> dict:
    """解析 TypeScript 对象字面量"""
    s = s.strip()
    if not s.startswith('{') or not s.endswith('}'):
        return {}

    inner = s[1:-1].strip()
    if not inner:
        return {}

    # 移除单行注释
    inner = re.sub(r'//.*?$', '', inner, flags=re.MULTILINE)
    # 移除多行注释
    inner = re.sub(r'/\*.*?\*/', '', inner, flags=re.DOTALL)

    result = {}
    # 按顶层键值对分割（考虑嵌套）
    depth = 0
    current = ''
    in_str = False
    str_char = None
    parts = []

    for c in inner:
        if in_str:
            current += c
            if c == '\\':
                continue
            if c == str_char:
                in_str = False
        else:
            if c in ('"', "'", '`'):
                in_str = True
                str_char = c
                current += c
            elif c in ('{', '['):
                depth += 1
                current += c
            elif c in ('}', ']'):
                depth -= 1
                current += c
            elif c == ',' and depth == 0:
                parts.append(current)
                current = ''
            else:
                current += c
    if current.strip():
        parts.append(current)

    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 查找第一个冒号（不在字符串内，不在嵌套内）
        colon_pos = -1
        depth = 0
        in_str = False
        str_char = None
        for i, c in enumerate(part):
            if in_str:
                if c == '\\':
                    continue
                if c == str_char:
                    in_str = False
            else:
                if c in ('"', "'", '`'):
                    in_str = True
                    str_char = c
                elif c in ('{', '['):
                    depth += 1
                elif c in ('}', ']'):
                    depth -= 1
                elif c == ':' and depth == 0:
                    colon_pos = i
                    break

        if colon_pos == -1:
            continue

        key = part[:colon_pos].strip()
        value_str = part[colon_pos + 1:].strip()

        # 移除键的引号
        if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
            key = key[1:-1]

        # 跳过注释键
        if '/*' in key or '*/' in key or key.strip() == '':
            continue

        result[key] = parse_ts_value(value_str)

    return result


def extract_node_types(ts_content: str) -> dict:
    """从 profile TypeScript 文件中提取 nodeTypes（使用 Node.js 解析器）"""
    import subprocess
    import tempfile

    # 创建临时文件存储 TypeScript 内容
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False, encoding='utf-8') as f:
        f.write(ts_content)
        temp_path = f.name

    try:
        # 调用 Node.js 解析器
        result = subprocess.run(
            ['node', str(Path(__file__).parent / 'parse_profiles.js')],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        # 返回第一个 profile 的结果（因为每次只解析一个文件）
        for profile_data in data.values():
            return profile_data
        return {}
    except Exception:
        return {}
    finally:
        Path(temp_path).unlink(missing_ok=True)


def extract_form_fields(node_schema: dict) -> list[dict]:
    """从 NodeSchema 中提取表单字段"""
    form = node_schema.get('form', [])
    if not isinstance(form, list):
        return []

    fields = []
    for field in form:
        if not isinstance(field, dict):
            continue
        fields.append({
            'key': field.get('key', ''),
            'label': field.get('label', ''),
            'type': field.get('type', 'text'),
            'required': field.get('required', False),
            'dsTypes': field.get('dsTypes', []),
            'hasWhen': 'when' in field,
            'hasOnChange': 'onChange' in field,
            'hasPick': 'pick' in field,
        })
    return fields


def determine_execution_model(type_name: str, node_schema: dict) -> str:
    """确定执行模型"""
    if type_name in WORKER_TYPES:
        return 'dag-engine'
    if type_name in MASTER_HANDLER_TYPES:
        return 'passthrough'
    if type_name in TEMPLATE_TYPES:
        return 'template'
    if type_name in RUNTIME_ONLY_TYPES:
        return 'dag-engine'
    # 检查是否有 page 或 template 标记
    if node_schema.get('page') or node_schema.get('template'):
        return 'nonExecutable'
    return 'demo-only'


def determine_route(type_name: str, execution_model: str) -> str:
    """确定路由目标"""
    if execution_model == 'dag-engine':
        if type_name in WORKER_TYPES:
            return 'worker'
        return 'master'
    if execution_model == 'passthrough':
        return 'master'
    if execution_model == 'template':
        return 'template'
    return 'UNROUTED'


def generate_component(type_name: str, profile: str, node_schema: dict, dag_relevant: bool) -> dict:
    """生成组件目录条目"""
    execution_model = determine_execution_model(type_name, node_schema)
    route = determine_route(type_name, execution_model)
    form_fields = extract_form_fields(node_schema)

    # 提取 categories
    categories = node_schema.get('categories', [])
    if not isinstance(categories, list):
        categories = []

    # 提取 palette 信息
    palette_visible = node_schema.get('paletteVisible', True)
    palette_group = node_schema.get('paletteGroup', '')
    palette_index = node_schema.get('paletteIndex', 0)

    # 提取 flags
    flags = {
        'hasSummaryFn': 'summary' in node_schema,
        'hasPage': 'page' in node_schema,
        'hasTemplate': 'template' in node_schema,
        'hasPortsFn': 'ports' in node_schema,
    }

    return {
        'type': type_name,
        'profile': profile,
        'dagRelevant': dag_relevant,
        'executionModel': execution_model,
        'executionNote': EXECUTION_MODELS.get(execution_model, ''),
        'code': node_schema.get('code'),
        'label': node_schema.get('label', type_name),
        'icon': node_schema.get('icon', ''),
        'color': node_schema.get('color', '#666'),
        'desc': node_schema.get('desc', ''),
        'phase': node_schema.get('phase'),
        'categories': categories,
        'shape': node_schema.get('shape'),
        'runtimeOnly': type_name in RUNTIME_ONLY_TYPES,
        'route': route,
        'executor': None,
        'paletteVisible': palette_visible,
        'paletteGroup': palette_group,
        'paletteIndex': palette_index,
        'formFieldCount': len(form_fields),
        'formFields': form_fields,
        'defaultKeys': list(node_schema.get('defaults', {}).keys()) if isinstance(node_schema.get('defaults'), dict) else [],
        'flags': flags,
    }


def generate_catalog() -> dict:
    """生成完整的 dag_catalog.json"""
    import subprocess

    # 调用 Node.js 解析器获取所有 profile 数据
    result = subprocess.run(
        ['node', str(Path(__file__).parent / 'parse_profiles.js')],
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    if result.returncode != 0:
        raise RuntimeError(f"Node.js parser failed: {result.stderr}")

    all_profiles_data = json.loads(result.stdout)

    components = []
    profiles_info = []
    all_types = set()
    backend_only_types = []
    unrouted_types = []
    cross_profile_duplicates = {}

    for profile_id, filename in PROFILE_FILES.items():
        node_types = all_profiles_data.get(profile_id, {})

        # Profile 信息
        profile_info = {
            'profile': profile_id,
            'source': f'datara-web/src/graph/profiles/{filename}',
            'nodeTypes': len(node_types),
            'dagRelevant': profile_id == 'dag',
            'paletteFormat': 'items' if profile_id in ('dag', 'stream') else 'types',
            'paletteGroups': 0,
            'paletteItems': len(node_types),
            'paletteSpreads': [],
            'hidden': 0,
        }
        profiles_info.append(profile_info)

        # 处理每个 type
        for type_name, schema in node_types.items():
            if type_name in all_types:
                if type_name not in cross_profile_duplicates:
                    cross_profile_duplicates[type_name] = []
                cross_profile_duplicates[type_name].append(profile_id)
                continue

            all_types.add(type_name)
            component = generate_component(type_name, profile_id, schema, profile_id == 'dag')
            components.append(component)

            if type_name in MASTER_HANDLER_TYPES and type_name not in node_types:
                backend_only_types.append(type_name)

            if component['route'] == 'UNROUTED':
                unrouted_types.append(type_name)

    # 计算统计信息
    stats = {
        'profiles': len(profiles_info),
        'profilesWithNodeTypes': sum(1 for p in profiles_info if p['nodeTypes'] > 0),
        'total': len(components),
        'paletteVisible': sum(1 for c in components if c['paletteVisible']),
        'hidden': sum(1 for c in components if not c['paletteVisible']),
        'routable': sum(1 for c in components if c['route'] != 'UNROUTED'),
        'dagTotal': sum(1 for c in components if c['profile'] == 'dag'),
        'dagRoutable': sum(1 for c in components if c['profile'] == 'dag' and c['route'] != 'UNROUTED'),
        'backendOnlyTypes': backend_only_types,
        'backendOnlyCount': len(backend_only_types),
        'template': sum(1 for c in components if c['executionModel'] == 'template'),
        'nonExecutable': sum(1 for c in components if c['executionModel'] == 'nonExecutable'),
        'unrouted': len(unrouted_types),
        'unroutedTypes': unrouted_types,
        'unroutedTotal': len(unrouted_types),
        'unroutedByProfile': {},
        'runtimeOnly': len(RUNTIME_ONLY_TYPES),
        'formFieldCount': sum(c['formFieldCount'] for c in components),
        'formFieldTypeCount': len(set(f['type'] for c in components for f in c['formFields'])),
        'formFieldType': list(set(f['type'] for c in components for f in c['formFields'])),
        'nonSerializable': {
            'summary': sum(1 for c in components if c['flags']['hasSummaryFn']),
            'ports': sum(1 for c in components if c['flags']['hasPortsFn']),
        },
        'routeByProfile': {},
        'consistencyErrors': [],
        'duplicateTypeInProfile': [],
        'crossProfileDuplicateTypes': list(cross_profile_duplicates.keys()),
    }

    for c in components:
        if c['route'] == 'UNROUTED':
            profile = c['profile']
            if profile not in stats['unroutedByProfile']:
                stats['unroutedByProfile'][profile] = []
            stats['unroutedByProfile'][profile].append(c['type'])

    for c in components:
        profile = c['profile']
        route = c['route']
        if profile not in stats['routeByProfile']:
            stats['routeByProfile'][profile] = {}
        if route not in stats['routeByProfile'][profile]:
            stats['routeByProfile'][profile][route] = 0
        stats['routeByProfile'][profile][route] += 1

    catalog_json = json.dumps(components, sort_keys=True, ensure_ascii=False)
    catalog_hash = hashlib.sha256(catalog_json.encode('utf-8')).hexdigest()[:16]

    return {
        'schemaVersion': 1,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'source': [f'datara-web/src/graph/profiles/{f}' for f in PROFILE_FILES.values()],
        'scope': 'system',
        'note': 'M0 只读系统组件目录，覆盖全部 7 个 ViewProfile。用户自建组件（M1+）以 scope=user 另行下发，不在本文件内。',
        'stats': stats,
        'profiles': profiles_info,
        'components': components,
        'catalogHash': catalog_hash,
    }


def main():
    parser = argparse.ArgumentParser(description='Generate dag_catalog.json from frontend profiles')
    parser.add_argument('--output', '-o', default='common/dag_catalog.json', help='Output file path')
    args = parser.parse_args()

    catalog = generate_catalog()

    output_path = BACKEND_DIR / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    print(f"Generated {output_path}")
    print(f"  Total components: {catalog['stats']['total']}")
    print(f"  Palette visible: {catalog['stats']['paletteVisible']}")
    print(f"  Unrouted: {catalog['stats']['unrouted']}")
    print(f"  Catalog hash: {catalog['catalogHash']}")


if __name__ == '__main__':
    main()
