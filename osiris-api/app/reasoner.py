from typing import Any
import httpx
import json
from model_orchestrator import choose_model

from cognition import build_execution_plan
from cognition_executor import execute_plan
from memory import save_memory
from self_reflection import evaluate_execution
from learning import store_learning


OLLAMA_URL = "http://ollama:11434"
REASONING_MODEL = choose_model("reasoning")


def compact_execution(execution: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "status": execution.get("status"),
        "steps_executed": execution.get("steps_executed"),
        "results": [],
    }

    for result in execution.get("results", []):
        compact["results"].append({
            "step": result.get("step"),
            "status": result.get("status"),
            "output": result.get("output"),
        })

    return compact


def deterministic_summary(goal: str, plan: list[str], execution: dict[str, Any], reflection: dict[str, Any]) -> str:
    lines = [
        f"Goal: {goal}",
        "",
        "I executed this plan:",
    ]

    for step in plan:
        lines.append(f"- {step}")

    lines.append("")
    lines.append("Results:")

    for result in execution.get("results", []):
        lines.append(
            f"- {result.get('step', 'unknown')}: "
            f"{result.get('status', 'unknown')} - "
            f"{result.get('output', '')}"
        )

    lines.append("")
    lines.append(f"Reflection score: {reflection.get('score')}/100")

    problems = reflection.get("problems", [])
    if problems:
        lines.append("Problems detected:")
        for problem in problems:
            lines.append(f"- {problem}")
    else:
        lines.append("No execution problems detected.")

    lines.append("")
    lines.append("No code changes were made. No patches were applied.")
    lines.append("Next best step: review the discovered TODO matches and then run a targeted code review on the relevant file.")

    return "\n".join(lines)


async def synthesize_agent_result(
    goal: str,
    plan: list[str],
    execution: dict[str, Any],
    reflection: dict[str, Any],
) -> str:
    safe_execution = compact_execution(execution)

    prompt = f"""
You are Osiris, a local autonomous engineering assistant.

The user goal was:
{goal}

The execution plan was:
{json.dumps(plan, indent=2)}

The ACTUAL execution result was:
{json.dumps(safe_execution, indent=2)}

The self-reflection result was:
{json.dumps(reflection, indent=2)}

Write a clear final answer for the user.

STRICT RULES:
- Use ONLY the actual execution result above.
- Never invent actions.
- Never say a patch was created, applied, denied, restored, or backed up unless the execution result explicitly contains that patch action.
- Never invent file paths, backup paths, changed files, or fixes.
- If no patch action occurred, explicitly say: "No code changes were made."
- Mention the reflection score.
- End with the next best engineering step.
""".strip()

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": REASONING_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You summarize tool execution truthfully. You never invent actions.",
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    "stream": False,
                    "keep_alive": "30m",
                },
            )

            response.raise_for_status()
            data = response.json()

        answer = data.get("message", {}).get("content", "").strip()

        if not answer:
            return deterministic_summary(goal, plan, execution, reflection)

        forbidden = [
            "patch applied successfully",
            "backup:",
            "[file_path]",
            "[backup_path]",
        ]

        if any(term in answer.lower() for term in forbidden):
            return deterministic_summary(goal, plan, execution, reflection)

        return answer

    except Exception:
        return deterministic_summary(goal, plan, execution, reflection)


async def run_reasoning_loop(goal: str, max_rounds: int = 3) -> dict[str, Any]:
    max_rounds = max(1, min(max_rounds, 3))
    rounds = []

    for round_index in range(max_rounds):
        plan = build_execution_plan(goal)
        execution = await execute_plan(plan, message=goal)
        reflection = evaluate_execution(execution)

        rounds.append({
            "round": round_index + 1,
            "plan": plan,
            "execution": execution,
            "reflection": reflection,
        })

        if reflection.get("success"):
            break

    final_round = rounds[-1]

    final_summary = await synthesize_agent_result(
        goal=goal,
        plan=final_round["plan"],
        execution=final_round["execution"],
        reflection=final_round["reflection"],
    )

    try:
        await store_learning(
            goal=goal,
            plan=final_round["plan"],
            reflection=final_round["reflection"],
            notes=final_summary,
        )
    except Exception as exc:
        print(f"[Learning Error] {type(exc).__name__}: {str(exc)}")

    try:
        await save_memory(
            memory_type="agent_run",
            title=f"Agent run: {goal[:80]}",
            content=final_summary,
            metadata={
                "goal": goal,
                "rounds": len(rounds),
                "status": "complete",
                "plan": final_round["plan"],
                "reflection": final_round["reflection"],
            },
        )
    except Exception as exc:
        print(f"[Memory Error] {type(exc).__name__}: {str(exc)}")

    return {
        "type": "agent_run",
        "command": "agent_loop",
        "goal": goal,
        "answer": final_summary,
        "data": {
            "rounds": rounds,
        },
    }
