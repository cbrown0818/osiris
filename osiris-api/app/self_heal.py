from typing import Any

from patch_core import generate_patch_with_ai
from memory import save_memory
from model_orchestrator import choose_model


async def propose_self_heal_patch(file_path: str, issue: str) -> dict[str, Any]:
    model = choose_model("code_patch")

    instruction = (
        "Make the smallest safe fix for this issue. "
        "Do not rewrite unrelated logic. "
        "Do not remove existing behavior. "
        "Preserve current API compatibility. "
        f"Issue: {issue}"
    )

    result = await generate_patch_with_ai(
        file_path=file_path,
        instruction=instruction,
        model=model,
    )

    patch = result.get("patch", {})

    try:
        await save_memory(
            memory_type="self_heal_proposal",
            title=f"Self-heal proposed: {file_path}",
            content=f"Issue: {issue}",
            metadata={
                "file_path": file_path,
                "issue": issue,
                "patch_id": patch.get("id"),
                "model": model,
            },
        )
    except Exception as exc:
        print(f"[Memory Error] {type(exc).__name__}: {str(exc)}")

    return result
