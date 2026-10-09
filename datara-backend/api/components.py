"""Compatibility access to the shared component catalog.

HTTP routes are intentionally defined only by :mod:`api.component`; importing
this module must never register a second /components/catalog endpoint.
"""

from common.component_catalog import catalog_payload

__all__ = ["catalog_payload"]
