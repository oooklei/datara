"""Datara ai_copilot — R8-V Vanna PoC module (plan step 1 skeleton).

Sovereignty boundary (design D6): this package wraps vanna behind Datara
contract types. Only ``adapter.py`` may import vanna; every other module
in this package deals in plain Datara types. SQL generation never
executes; execution enters exclusively through the R8-A authorized
bridge (plan step 3).
"""
