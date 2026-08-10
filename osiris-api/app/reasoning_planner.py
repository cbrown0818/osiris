from __future__ import annotations

from typing import Any

from cognition import build_execution_plan


def build_reasoning_plan(goal: str) -> dict[str, Any]:
    """
    Build a proposed OSIRIS plan without executing anything.

    This function is intentionally side-effect free:
    - no tool execution
    - no file changes
    - no memory writes
    - no learning writes
    - no device actions
    """
    if not isinstance(goal, str):
        raise ValueError("goal must be a string")

    clean_goal = goal.strip()

    if not clean_goal:
        raise ValueError("goal cannot be empty")

    plan = build_execution_plan(clean_goal)

    return {
        "goal": clean_goal,
        "mode": "planning_only",
        "plan": list(plan),
        "step_count": len(plan),
        "executed": False,
        "requires_execution_authorization": True,
    }
