import os
import re
import json

def process_outages():
    path = "src/obsidian_rl/data/outages.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Replace VenueOutage.identity
    old_venue = """    @property
    def identity(self) -> str:
        \"\"\"Deterministic hash of this outage entry.\"\"\"
        data = json.dumps(
            {
                "venue": self.venue,
                "start_ms": self.start_ms,
                "end_ms": self.end_ms,
                "source_id": self.source_id,
                "source_content_hash": self.source_content_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()"""
    
    new_venue = """    @property
    def identity(self) -> str:
        \"\"\"Deterministic hash of this outage entry.\"\"\"
        data = json.dumps(
            {
                "venue": self.venue,
                "start_ms": self.start_ms,
                "end_ms": self.end_ms,
                "source_id": self.source_id,
                "verification_timestamp_ms": self.verification_timestamp_ms,
                "source_content_hash": self.source_content_hash,
                "reason": self.reason,
                "affected_symbols": sorted(self.affected_symbols),
                "venue_wide": self.venue_wide,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()"""
    
    content = content.replace(old_venue, new_venue)

    old_reg = """    def identity(self) -> str:
        \"\"\"Deterministic hash of the sorted outage identities.\"\"\"
        if not self._outages:
            return "empty"
        import hashlib
        h = hashlib.sha256()
        for o in self._outages:
            h.update(o.identity.encode('utf-8'))
        return h.hexdigest()"""

    new_reg = """    def identity(self) -> str:
        \"\"\"Deterministic hash of the sorted outage identities.\"\"\"
        import hashlib
        import json
        outages_list = [o.identity for o in self._outages]
        h = hashlib.sha256(json.dumps(outages_list, sort_keys=True).encode("utf-8"))
        return h.hexdigest()"""

    content = content.replace(old_reg, new_reg)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

process_outages()
print("Outages fixed")
