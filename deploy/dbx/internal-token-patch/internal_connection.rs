//! DBX connection credentials for the Datara orchestration gateway only.

use std::net::SocketAddr;
use std::sync::Arc;

use axum::extract::{ConnectInfo, Path, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::IntoResponse;
use axum::Json;

use crate::internal_auth::{
    datara_gateway_only, internal_peer_allowed, internal_token, internal_token_matches,
};
use crate::state::WebState;

pub(crate) async fn connection_params(
    State(state): State<Arc<WebState>>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    Path(connection_id): Path<String>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, StatusCode> {
    let supplied = headers
        .get("x-datara-internal-token")
        .and_then(|value| value.to_str().ok())
        .unwrap_or("");
    let Some(expected) = internal_token().filter(|_| datara_gateway_only()) else {
        tracing::warn!(peer = %peer.ip(), connection_id, "dbx_internal_connection_disabled");
        return Err(StatusCode::SERVICE_UNAVAILABLE);
    };
    if !internal_token_matches(expected, supplied) {
        tracing::warn!(peer = %peer.ip(), connection_id, "dbx_internal_connection_denied_token");
        return Err(StatusCode::UNAUTHORIZED);
    }
    let allowlist = std::env::var("DBX_INTERNAL_ALLOWED_CIDRS").unwrap_or_default();
    if !internal_peer_allowed(peer.ip(), &allowlist) {
        tracing::warn!(peer = %peer.ip(), connection_id, "dbx_internal_connection_denied_peer");
        return Err(StatusCode::FORBIDDEN);
    }
    let configs = state.app.storage.load_connections().await.map_err(|_| {
        tracing::error!(peer = %peer.ip(), connection_id, "dbx_internal_connection_storage_failed");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;
    let config = configs
        .into_iter()
        .find(|row| row.id == connection_id)
        .ok_or_else(|| {
            tracing::info!(peer = %peer.ip(), connection_id, "dbx_internal_connection_not_found");
            StatusCode::NOT_FOUND
        })?;
    tracing::info!(peer = %peer.ip(), connection_id, "dbx_internal_connection_params_read");
    // `Storage::load_connections` hydrates the password and transport-layer
    // secrets from DBX's secret store in v0.6.29. Return that hydrated config
    // directly; newer DBX releases expose an additional resolver method, but
    // it is not present in the 0.6.29 WebState API.
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(config)))
}
