from typing import Any
from memory import save_memory


async def store_learning(
    goal: str,
    plan: list[str],
    reflection: dict[str, Any],
    notes: str = "",
) -> None:
    await save_memory(
        memory_type="learning",
        title=f"Learning: {goal[:80]}",
        content=notes or f"Goal: {goal} | Success: {reflection.get('success')} | Score: {reflection.get('score')}",
        metadata={
            "goal": goal,
            "plan": plan,
            "success": reflection.get("success"),
            "score": reflection.get("score"),
            "problems": reflection.get("problems", []),
        },
    )
