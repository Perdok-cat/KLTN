"""GCP service-to-service authentication helper.

When the frontend Cloud Run service calls the backend Cloud Run service
(which requires authentication), every request must carry an OIDC identity
token fetched from the GCP metadata server.

Usage:
    from utils.gcp_auth import auth_headers
    requests.get(url, headers=auth_headers(), timeout=10)
"""
from __future__ import annotations

import os

import requests
import streamlit as st

_MV_API_URL: str = os.getenv("MV_API_URL", "http://localhost:5001")
_IS_LOCAL: bool = "localhost" in _MV_API_URL or "127.0.0.1" in _MV_API_URL

_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1"
    "/instance/service-accounts/default/identity"
)


@st.cache_data(ttl=3300, show_spinner=False)
def _fetch_id_token(audience: str) -> str | None:
    """Fetch an OIDC identity token from the GCP metadata server.

    Tokens are valid for 1 hour; cached for 55 minutes to avoid expiry races.
    Returns None when running locally or when the metadata server is unreachable.
    """
    try:
        resp = requests.get(
            _METADATA_TOKEN_URL,
            params={"audience": audience},
            headers={"Metadata-Flavor": "Google"},
            timeout=3,
        )
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None


def auth_headers(audience: str | None = None) -> dict[str, str]:
    """Return an Authorization header dict for Cloud Run service-to-service calls.

    Falls back to an empty dict when running locally so local development works
    without any GCP credentials.
    """
    if _IS_LOCAL:
        return {}
    target = (audience or _MV_API_URL).rstrip("/")
    token = _fetch_id_token(target)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
