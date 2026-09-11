import os
import re

path = "src/obsidian_rl/data/outages.py"
with open(path, "r") as f:
    code = f.read()

old_registry = """class OutageRegistry:
    \"\"\"Immutable registry of confirmed venue outages.\"\"\"

    def __init__(self, outages: tuple[VenueOutage, ...] = ()) -> None:
        self._outages = outages

    @property
    def outages(self) -> tuple[VenueOutage, ...]:
        return self._outages"""

new_registry = """class OutageRegistry:
    \"\"\"Immutable registry of confirmed venue outages.\"\"\"

    def __init__(self, outages: tuple[VenueOutage, ...] = ()) -> None:
        self._outages = tuple(sorted(outages, key=lambda x: x.identity))

    @property
    def outages(self) -> tuple[VenueOutage, ...]:
        return self._outages

    def identity(self) -> str:
        \"\"\"Deterministic hash of the sorted outage identities.\"\"\"
        if not self._outages:
            return "empty"
        import hashlib
        h = hashlib.sha256()
        for o in self._outages:
            h.update(o.identity.encode('utf-8'))
        return h.hexdigest()"""

code = code.replace(old_registry, new_registry)

with open(path, "w") as f:
    f.write(code)
