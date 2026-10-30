//! Internal data API channel for Datara's owner-filtering gateway.

pub(crate) fn internal_token() -> Option<&'static str> {
    static TOKEN: std::sync::OnceLock<Option<String>> = std::sync::OnceLock::new();
    TOKEN
        .get_or_init(|| std::env::var("DBX_INTERNAL_TOKEN").ok().filter(|value| token_is_long_enough(value)))
        .as_deref()
}

pub(crate) fn datara_gateway_only() -> bool {
    static ENABLED: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *ENABLED.get_or_init(|| {
        gateway_only_enabled(std::env::var("DBX_DATARA_GATEWAY_ONLY").ok().as_deref())
    })
}

fn gateway_only_enabled(value: Option<&str>) -> bool {
    value == Some("1")
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

pub(crate) fn internal_peer_allowed(peer: std::net::IpAddr, allowed_cidrs: &str) -> bool {
    allowed_cidrs.split(',').map(str::trim).filter(|entry| !entry.is_empty()).any(|entry| {
        let (address, prefix) = match entry.split_once('/') {
            Some((address, prefix)) => (address, Some(prefix)),
            None => (entry, None),
        };
        let Ok(network) = address.parse::<std::net::IpAddr>() else { return false };
        let bits = match network { std::net::IpAddr::V4(_) => 32, std::net::IpAddr::V6(_) => 128 };
        let length = match prefix { Some(raw) => match raw.parse::<u32>() {
            Ok(value) if value <= bits => value,
            _ => return false,
        }, None => bits };
        match (peer, network) {
            (std::net::IpAddr::V4(peer), std::net::IpAddr::V4(network)) => {
                let mask = if length == 0 { 0 } else { u32::MAX << (32 - length) };
                (u32::from(peer) & mask) == (u32::from(network) & mask)
            }
            (std::net::IpAddr::V6(peer), std::net::IpAddr::V6(network)) => {
                let mask = if length == 0 { 0 } else { u128::MAX << (128 - length) };
                (u128::from(peer) & mask) == (u128::from(network) & mask)
            }
            _ => false,
        }
    })
}

pub(crate) fn internal_api_allowed(suffix: &str) -> bool {
    matches!(
        suffix,
        "migration/status" | "plugins" | "version"
            | "app-settings/sql-file-upload-max-bytes"
            | "layout/sidebar" | "layout/table-vgroups"
            | "ssh/prompts" | "ssh/prompts/pending"
            | "prompt-templates"
    ) || suffix == "history"
        || suffix.starts_with("history/")
        || suffix == "saved-sql"
        || ["connection/", "schema/", "query/", "mq/", "ai/", "saved-sql/", "tunnel-profiles/", "prompt-templates/"]
            .iter()
            .any(|prefix| suffix.starts_with(prefix))
}

#[cfg(test)]
mod tests {
    use super::{gateway_only_enabled, internal_api_allowed, internal_peer_allowed, internal_token_matches, token_is_long_enough};

    #[test]
    fn gateway_only_mode_requires_explicit_opt_in() {
        assert!(gateway_only_enabled(Some("1")));
        for value in [None, Some("0"), Some("true"), Some("")] {
            assert!(!gateway_only_enabled(value));
        }
    }

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
    fn secret_endpoint_requires_explicit_peer_allowlist() {
        let peer = "172.19.0.5".parse().unwrap();
        assert!(!internal_peer_allowed(peer, ""));
        assert!(internal_peer_allowed(peer, "172.19.0.0/16"));
        assert!(!internal_peer_allowed(peer, "172.20.0.0/16"));
        assert!(!internal_peer_allowed(peer, "172.19.0.0/33"));
        assert!(!internal_peer_allowed(peer, "garbage"));
        assert!(internal_peer_allowed("::1".parse().unwrap(), "::1/128"));
    }

    #[test]
    fn internal_channel_covers_owner_gateway_routes_but_not_dbx_login() {
        for path in ["connection/list", "tunnel-profiles/list", "prompt-templates", "ai/configs", "migration/status", "layout/sidebar"] {
            assert!(internal_api_allowed(path), "{path}");
        }
        for path in ["auth/login", "auth/check", "auth/setup", "unknown/operation"] {
            assert!(!internal_api_allowed(path), "{path}");
        }
    }

    #[test]
    fn only_data_apis_use_internal_channel() {
        for path in ["connection/list", "schema/columns", "query/execute", "history/search", "saved-sql", "ai/conversations"] {
            assert!(internal_api_allowed(path));
        }
        for path in ["auth/change-password", "app-settings/config/decrypt", "backup/restore"] {
            assert!(!internal_api_allowed(path));
        }
    }
}
