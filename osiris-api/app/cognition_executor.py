from typing import Any

from dev_core import list_tree, search_project, read_file


def choose_search_query(message: str) -> str:
    text = message.lower()

    if "todo" in text:
        return "TODO"

    if "memory" in text:
        return "memory"

    if "document" in text or "pdf" in text:
        return "document"

    if "patch" in text:
        return "patch"

    if "slow" in text or "timeout" in text:
        return "timeout"

    if "performance" in text or "speed" in text or "efficient" in text:
        return "async"

    if "optimize" in text or "codebase" in text or "analyze" in text:
        return "def "

    return "def "


async def execute_plan(plan: list[str], message: str = "") -> dict[str, Any]:
    results = []
    context: dict[str, Any] = {
        "message": message,
        "search_query": None,
        "search_results": [],
        "files_read": [],
    }

    for step in plan:
        try:
            if step == "dev_tree":
                data = list_tree(max_depth=3)
                output = f"Project tree inspected. Found {data.get('count')} items."

            elif step == "dev_search":
                query = choose_search_query(message)
                data = search_project(query=query, max_results=25)

                context["search_query"] = query
                context["search_results"] = data.get("results", [])

                output = (
                    f"Project search completed for '{query}'. "
                    f"Found {data.get('count')} matches."
                )

            elif step == "dev_read":
                target = None

                if context.get("search_results"):
                    target = context["search_results"][0].get("path")

                if not target:
                    target = "osiris-api/app/assistant_router.py"

                data = read_file(target, max_bytes=40000)

                context["files_read"].append(target)

                output = f"Read {target}. Size: {data.get('size_bytes')} bytes."

            else:
                data = None
                output = "No executor available for this step."

            results.append({
                "step": step,
                "status": "success",
                "output": output,
                "data": data,
            })

        except Exception as exc:
            results.append({
                "step": step,
                "status": "error",
                "output": f"{type(exc).__name__}: {str(exc)}",
                "data": None,
            })

    return {
        "status": "complete",
        "steps_executed": len(results),
        "context": context,
        "results": results,
    }
