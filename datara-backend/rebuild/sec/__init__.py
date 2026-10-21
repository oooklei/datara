"""Security domain (rebuild/sec): platform-wide access audit.

Scope (governance ruling 2026-10-22): access audit only. Data masking is
explicitly out of scope for this release; the domain reserves its name for
future extension without implementing any masking model or endpoint.

Migration mapping source: legacy front-end demo mock semantics
(``AccessLog`` in the retired datara-web demo) used as the modeling
reference per the five-step rule, section 3 of the governing design.
"""
