import os

engine_path = "src/obsidian_rl/portfolio/engine.py"
with open(engine_path, "r") as f:
    engine_code = f.read()

# Remove the silent clamping:
#         if approved < 0 and not self.config.allow_short:
#             approved, reason = 0.0, "short exposure disabled"

old_approve = """    def _approve_target(self, proposed: float) -> tuple[float, str | None]:
        limit = self.config.max_abs_exposure
        approved = max(-limit, min(limit, proposed))
        reason = None
        if approved != proposed:
            reason = f"target clamped from {proposed} to {approved}"
        if approved < 0 and not self.config.allow_short:
            approved, reason = 0.0, "short exposure disabled"
        return approved, reason"""

new_approve = """    def _approve_target(self, proposed: float) -> tuple[float, str | None]:
        if proposed < 0 and not self.config.allow_short:
            raise ValueError(f"short exposure disabled but requested target: {proposed}")
        limit = self.config.max_abs_exposure
        approved = max(-limit, min(limit, proposed))
        reason = None
        if approved != proposed:
            reason = f"target clamped from {proposed} to {approved}"
        return approved, reason"""

engine_code = engine_code.replace(old_approve, new_approve)

with open(engine_path, "w") as f:
    f.write(engine_code)
