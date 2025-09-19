"""YAML-based policy loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml  # type: ignore[import-untyped]

from .models import PolicyBundle, PolicyCondition, PolicyEffect, PolicyRule


def _load_rules(path: Path) -> List[PolicyRule]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules: List[PolicyRule] = []
    for raw in data.get("rules", []):
        rid = raw.get("id")
        if not rid:
            continue
        cond = PolicyCondition(**(raw.get("when", {})))
        eff = PolicyEffect(**(raw.get("effects", {})))
        rules.append(PolicyRule(id=rid, description=raw.get("description", ""), priority=int(raw.get("priority", 0)), condition=cond, effect=eff))
    rules.sort(key=lambda r: r.priority, reverse=True)
    return rules


def load_policy_bundle(base_path: Path) -> PolicyBundle:
    content_path = base_path / "content_policies.yaml"
    style_path = base_path / "style_policies.yaml"
    safety_path = base_path / "safety_policies.yaml"
    return PolicyBundle(
        content=_load_rules(content_path),
        style=_load_rules(style_path),
        safety=_load_rules(safety_path),
    )


def bundle_to_dict(bundle: PolicyBundle) -> Dict[str, List[Dict[str, Any]]]:
    def serialize(rules: Iterable[PolicyRule]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for rule in rules:
            out.append(
                {
                    "id": rule.id,
                    "description": rule.description,
                    "priority": rule.priority,
                    "when": rule.condition.__dict__,
                    "effects": rule.effect.__dict__,
                }
            )
        return out

    return {
        "content": serialize(bundle.content),
        "style": serialize(bundle.style),
        "safety": serialize(bundle.safety),
    }
