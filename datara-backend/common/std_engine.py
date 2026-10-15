import re
from common.dsconn import quote_ident
def check_name(value, pattern=None):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value or ""): return False
    return not pattern or bool(re.fullmatch(pattern, value))
def check_type(actual, expected, length=None, expected_length=None):
    return str(actual).upper()==str(expected).upper() and (expected_length is None or length is None or int(length)<=int(expected_length))
def check_code(value, values):
    return value in {str(v.get("c",v)) for v in values}
def validate_target(value): return quote_ident(value.split(".")[-1])

