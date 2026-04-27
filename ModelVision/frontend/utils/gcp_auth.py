"""HTTP helper for calling the ModelVision backend.

Backend is deployed publicly (--allow-unauthenticated) so no OIDC token is
required. This module is kept so existing call-sites (auth_headers()) continue
to work without any changes.
"""


def auth_headers(*_args, **_kwargs) -> dict:
    """Return an empty header dict – backend is public, no auth needed."""
    return {}
