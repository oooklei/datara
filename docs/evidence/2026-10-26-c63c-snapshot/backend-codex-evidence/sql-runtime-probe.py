from worker.executors.sql import _is_readonly_statement

assert _is_readonly_statement("SELECT 1")
assert not _is_readonly_statement("SELECT GET_LOCK('x', 0)")
assert not _is_readonly_statement("SELECT @x := 1")
assert not _is_readonly_statement("SELECT unknown_side_effect()")
print("IMPORT_POLICY_OK")
