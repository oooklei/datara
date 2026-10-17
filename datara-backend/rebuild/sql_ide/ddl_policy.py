"""Conservative, side-effect-free policy checks for SQL IDE DDL previews."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


SUPPORTED_DIALECTS = frozenset({"mysql", "postgresql", "sqlite"})
SUPPORTED_OBJECT_KINDS = frozenset({"table", "view", "function", "procedure", "trigger"})
_DDL_STARTS = frozenset({"CREATE", "ALTER", "DROP", "TRUNCATE"})
_OBJECT_WORDS = {
    "table": frozenset({"TABLE"}),
    "view": frozenset({"VIEW"}),
    "function": frozenset({"FUNCTION"}),
    "procedure": frozenset({"PROCEDURE", "PROC"}),
    "trigger": frozenset({"TRIGGER"}),
}


@dataclass(frozen=True)
class DdlFinding:
    level: str
    code: str
    message: str
    impacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class DdlPolicyResult:
    dialect: str
    object_kind: str
    operation: str | None
    statement_count: int
    findings: tuple[DdlFinding, ...]
    blocked: bool


def _sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _sql_tokens_and_statement_count(sql: str) -> tuple[list[str], int, tuple[str, ...]]:
    """Tokenize words outside comments and quoted values.

    This is deliberately a small safety scanner, not a SQL parser. Incomplete
    lexical constructs are returned to the caller so they can never be treated
    as a clean preview.
    """
    tokens: list[str] = []
    word: list[str] = []
    lexical_errors: list[str] = []
    statements = 0
    has_nonspace = False
    index = 0
    quote: str | None = None
    while index < len(sql):
        char = sql[index]
        following = sql[index + 1] if index + 1 < len(sql) else ""
        if quote:
            if char == quote:
                if following == quote and quote in {"'", '"', "`"}:
                    index += 2
                    continue
                quote = None
            elif char == "\\":
                lexical_errors.append("backslash_escape_unclassified")
                index += 2
                continue
            index += 1
            continue
        if char in {"'", '"', "`"}:
            if word:
                tokens.append("".join(word).upper())
                word.clear()
            quote = char
            has_nonspace = True
            index += 1
            continue
        if (
            char == "-"
            and following == "-"
            and (index + 2 == len(sql) or sql[index + 2].isspace())
        ):
            if word:
                tokens.append("".join(word).upper())
                word.clear()
            index += 2
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and following == "*":
            if sql[index : index + 3] == "/*!":
                lexical_errors.append("executable_comment_unclassified")
            if word:
                tokens.append("".join(word).upper())
                word.clear()
            index += 2
            depth = 1
            while index < len(sql) and depth:
                pair = sql[index : index + 2]
                if pair == "/*":
                    depth += 1
                    index += 2
                elif pair == "*/":
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                lexical_errors.append("unterminated_block_comment")
            continue
        if char == ";":
            if word:
                tokens.append("".join(word).upper())
                word.clear()
            if has_nonspace:
                statements += 1
                has_nonspace = False
            index += 1
            continue
        if char.isalnum() or char == "_":
            word.append(char)
            has_nonspace = True
        elif char.isspace():
            if word:
                tokens.append("".join(word).upper())
                word.clear()
        elif not char.isspace():
            if word:
                tokens.append("".join(word).upper())
                word.clear()
            has_nonspace = True
        index += 1
    if word:
        tokens.append("".join(word).upper())
    if quote:
        lexical_errors.append("unterminated_quoted_value")
    if has_nonspace:
        statements += 1
    return tokens, statements, tuple(dict.fromkeys(lexical_errors))


# Public alias for sibling modules (run_sql PoC read-only gate): one conservative
# scanner reused, never a second tokenizer (§11 no-duplicate-engine red line).
sql_tokens_and_statement_count = _sql_tokens_and_statement_count


def _operation_and_object(tokens: list[str]) -> tuple[str | None, str | None]:
    if not tokens:
        return None, None
    operation = tokens[0]
    offset = 1
    if operation == "CREATE" and tokens[1:3] == ["OR", "REPLACE"]:
        offset = 3
    elif operation == "CREATE" and tokens[1:3] == ["OR", "ALTER"]:
        offset = 3
    while offset < len(tokens) and tokens[offset] in {"TEMP", "TEMPORARY", "UNIQUE", "IF", "NOT", "EXISTS"}:
        offset += 1
    return operation, tokens[offset] if offset < len(tokens) else None


def evaluate_ddl_policy(
    *,
    dialect: str,
    object_kind: str,
    current_definition: str | None,
    current_definition_digest: str | None,
    expected_definition: str,
) -> DdlPolicyResult:
    """Return local policy findings; this function never opens a connection or executes SQL."""
    normalized_dialect = dialect.strip().lower()
    normalized_kind = object_kind.strip().lower()
    findings: list[DdlFinding] = []
    tokens, statement_count, lexical_errors = _sql_tokens_and_statement_count(expected_definition)
    operation, ddl_object = _operation_and_object(tokens)

    if normalized_dialect not in SUPPORTED_DIALECTS:
        findings.append(DdlFinding("block", "unsupported_dialect", "No local policy is configured for this dialect."))
    if normalized_kind not in SUPPORTED_OBJECT_KINDS:
        findings.append(DdlFinding("block", "unsupported_object_kind", "This object kind is outside the DDL preview policy."))
    if not expected_definition.strip():
        findings.append(DdlFinding("block", "empty_definition", "Expected definition is empty."))
    for error in lexical_errors:
        message = {
            "unterminated_quoted_value": "SQL contains an unterminated quoted value.",
            "unterminated_block_comment": "SQL contains an unterminated block comment.",
            "backslash_escape_unclassified": "A quoted backslash escape is dialect-dependent and cannot be classified locally.",
            "executable_comment_unclassified": "MySQL executable comments are outside the local scanner's supported syntax.",
        }.get(error, "SQL contains a lexical construct the local scanner cannot classify safely.")
        findings.append(
            DdlFinding(
                "block",
                error,
                message,
            )
        )
    if statement_count != 1:
        findings.append(DdlFinding("block", "statement_count_invalid", "Preview accepts exactly one non-empty DDL statement."))
    if operation not in _DDL_STARTS:
        findings.append(DdlFinding("block", "not_ddl_statement", "Input does not start with a supported DDL operation."))
    if operation in {"CREATE", "ALTER"} and ddl_object is None:
        findings.append(DdlFinding("block", "ddl_object_missing", "DDL is missing a recognizable object kind."))
    if normalized_kind in _OBJECT_WORDS and ddl_object and ddl_object not in _OBJECT_WORDS[normalized_kind]:
        findings.append(DdlFinding("block", "object_kind_mismatch", "DDL object kind does not match the requested target kind."))

    destructive_tokens = {"DROP", "CASCADE", "TRUNCATE"}
    if any(token in destructive_tokens for token in tokens):
        findings.append(DdlFinding("block", "destructive_ddl", "Deletion or cascade operation detected; policy blocks this definition."))
    if operation == "ALTER" and any(
        tokens[index : index + 2] == ["DROP", "COLUMN"] for index in range(len(tokens) - 1)
    ):
        findings.append(DdlFinding("block", "drop_column", "Column deletion detected; policy blocks this definition."))

    current_exists = current_definition is not None
    if current_exists:
        if not current_definition.strip():
            findings.append(DdlFinding("block", "preimage_empty", "Current definition is empty and cannot serve as a reliable preimage."))
        if current_definition_digest is None:
            findings.append(DdlFinding("block", "preimage_digest_missing", "Current definition is missing a digest to bind the preimage."))
        elif _sha256(current_definition) != current_definition_digest.lower():
            findings.append(DdlFinding("block", "preimage_digest_mismatch", "Current definition does not match the supplied digest; reread it."))
        if operation == "CREATE":
            findings.append(DdlFinding("block", "create_existing_object", "Target already has a definition; local policy does not infer replacement semantics."))
    elif current_definition_digest is not None:
        findings.append(DdlFinding("block", "unexpected_preimage_digest", "A preimage digest was supplied without a current definition."))
    elif operation == "ALTER":
        findings.append(DdlFinding("block", "alter_missing_object", "Target has no current definition for ALTER."))

    if operation in {"CREATE", "ALTER"} and normalized_kind in _OBJECT_WORDS:
        findings.append(
            DdlFinding("warn", "target_identity_unverified", "Local preview cannot verify the schema and object name inside the DDL.")
        )
    findings.append(
        DdlFinding("warn", "dependency_analysis_unavailable", "No metadata service was consulted; dependency impact remains unknown.")
    )
    findings.append(
        DdlFinding("warn", "syntax_validation_unavailable", "No database parser was called; SQL syntax has not been validated.")
    )

    return DdlPolicyResult(
        dialect=normalized_dialect,
        object_kind=normalized_kind,
        operation=operation,
        statement_count=statement_count,
        findings=tuple(findings),
        blocked=any(finding.level == "block" for finding in findings),
    )
