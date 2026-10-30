//! Internal data API channel for Datara's owner-filtering gateway.

pub(crate) fn internal_token() -> Option<&'static str> {
    static TOKEN: std::sync::OnceLock<Option<String>> = std::sync::OnceLock::new();
    TOKEN
        .get_or_init(|| std::env::var("DBX_INTERNAL_TOKEN").ok().filter(|value| token_is_long_enough(value)))
        .as_deref()
}

fn token_is_long_enough(value: &str) -> bool {
    value.len() >= 32
}

pub(crate) fn internal_token_matches(expected: &str, supplied: &str) -> bool {
    let mut difference = expected.len() ^ supplied.len();
    for index in 0..expected.len().max(supplied.len()) {
        difference |= usize::from(
            expected.as_bytes().get(index).copied().unwrap_or(0)
                ^ supplied.as_bytes().get(index).copied().unwrap_or(0),
        );
    }
    difference == 0
}

pub(crate) fn internal_api_allowed(suffix: &str) -> bool {
    suffix == "history"
        || suffix.starts_with("history/")
        || suffix == "saved-sql"
        || ["connection/", "schema/", "query/", "mq/", "ai/", "saved-sql/"]
            .iter()
            .any(|prefix| suffix.starts_with(prefix))
}

#[cfg(test)]
mod tests {
    use super::{internal_api_allowed, internal_token_matches, token_is_long_enough};

    #[test]
    fn token_has_minimum_length() {
        assert!(!token_is_long_enough(&"a".repeat(31)));
        assert!(token_is_long_enough(&"a".repeat(32)));
    }

    #[test]
    fn token_requires_exact_value() {
        let expected = "a".repeat(32);
        assert!(internal_token_matches(&expected, &expected));
        assert!(!internal_token_matches(&expected, &"b".repeat(32)));
        assert!(!internal_token_matches(&expected, &"a".repeat(31)));
    }

    #[test]
    fn only_data_apis_use_internal_channel() {
        for path in ["connection/list", "schema/columns", "query/execute", "history/search", "saved-sql", "ai/conversations"] {
            assert!(internal_api_allowed(path));
        }
        for path in ["auth/change-password", "app-settings/config/decrypt", "backup/restore", "migration/status"] {
            assert!(!internal_api_allowed(path));
        }
    }
}
