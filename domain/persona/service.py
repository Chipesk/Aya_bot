"""Thin wrapper around persona loader to expose trait metadata."""
# mypy: ignore-errors
from __future__ import annotations

from typing import Dict, List

from persona.loader import PersonaManager as _PersonaManager


class PersonaService:
    def __init__(self, base_dir: str = "persona") -> None:
        self._manager = _PersonaManager(base_dir)

    def data(self) -> Dict[str, object]:
        persona, _, _ = self._manager.load()
        return persona

    def traits(self) -> List[str]:
        persona = self.data()
        identity = persona.get("identity", {})
        style = persona.get("style", {})
        traits: List[str] = []
        for key in ("tone", "avoid"):
            values = style.get(key)
            if isinstance(values, list):
                traits.extend(values)
        if isinstance(identity.get("city"), str):
            traits.append(identity["city"])
        return traits

    def render_system_prompt(self, world: dict | None, user: dict | None, dialog: dict | None = None) -> str:
        _, _, template = self._manager.load()
        persona = self.data()
        policy = (self._manager.base / "policy.md").read_text(encoding="utf-8")
        return template.render(
            persona=persona,
            policy=policy,
            policies_yaml=policy,
            world=world or {},
            user=user or {},
            dialog=dialog or {},
        )

    def reload(self) -> None:
        self._manager.reload()
