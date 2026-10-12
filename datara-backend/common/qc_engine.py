"""受控数据质量 SQL 生成器。"""
import re
from common.dsconn import quote_ident
RULE_TYPES={"null_check","dup_check","range_check","freshness_check","cross_table_check"}
_COND=re.compile(r"^[A-Za-z0-9_ .<>=!()'"+'"""'+r"+-]+$")
def validate_condition(value=""):
    value=(value or "").strip(); upper=value.upper()
    if not value: return ""
    if ";" in value or "--" in value or "/*" in value or " OR " in f" {upper} " or not _COND.fullmatch(value): raise ValueError("过滤条件仅允许安全的 AND 表达式")
    return value
def rule_sql(rule):
    typ=getattr(rule,"rule_type",None) if not isinstance(rule,dict) else rule.get("rule_type")
    get=lambda k,d="": getattr(rule,k,d) if not isinstance(rule,dict) else rule.get(k,d)
    if typ not in RULE_TYPES: raise ValueError("不支持的质量规则类型")
    table=quote_ident(get("table_name")); coln=get("column_name"); col=quote_ident(coln) if coln else "*"; params=get("params_json") or {}; f=validate_condition(params.get("filter","")); suffix=f" WHERE {f}" if f else ""
    if typ=="null_check": return f"SELECT COUNT(*) AS hit_count FROM {table}{suffix}{' AND ' if suffix else ' WHERE '}{col} IS NULL"
    if typ=="dup_check": return f"SELECT COUNT(*)-COUNT(DISTINCT {col}) AS hit_count FROM {table}{suffix}"
    if typ=="range_check":
        lo,hi=params.get("min"),params.get("max")
        if lo is None or hi is None: raise ValueError("范围规则需要 min/max")
        return f"SELECT COUNT(*) AS hit_count FROM {table}{suffix}{' AND ' if suffix else ' WHERE '}({col} < {float(lo)} OR {col} > {float(hi)})"
    if typ=="freshness_check":
        hours=int(params.get("hours",24))
        if hours<0 or hours>8760: raise ValueError("freshness hours 越界")
        return f"SELECT COUNT(*) AS hit_count FROM {table}{suffix}{' AND ' if suffix else ' WHERE '}{col} < NOW() - INTERVAL {hours} HOUR"
    other=params.get("other_table")
    if not other: raise ValueError("跨表规则需要 other_table")
    key=quote_ident(str(params.get("key",coln)))
    return f"SELECT COUNT(*) AS hit_count FROM {table} a LEFT JOIN {quote_ident(str(other))} b ON a.{key}=b.{key} WHERE b.{key} IS NULL"

