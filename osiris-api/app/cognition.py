def build_execution_plan(message: str) -> list[str]:
    text = message.lower()

    plan = []

    if any(x in text for x in ["code", "project", "optimize", "analyze"]):
        plan.append("dev_tree")
        plan.append("dev_search")
        plan.append("dev_read")

    elif any(x in text for x in ["gpu", "temperature", "vram"]):
        plan.append("gpu_status")

    elif any(x in text for x in ["document", "pdf", "book", "read it"]):
        plan.append("doc_query")

    elif any(x in text for x in ["patch", "fix bug"]):
        plan.append("patch_pending")

    else:
        plan.append("chat")

    return plan
