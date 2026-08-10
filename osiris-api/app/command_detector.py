"""Command phrase detection for Osiris assistant commands."""


def detect_priority_command(message: str) -> str:
    text = (message or "").lower().strip()

    if not text:
        return "chat"

    project_summary_phrases = {
        "project summary",
        "dev summary",
        "development summary",
        "summarize project",
        "summarize the project",
        "summarize osiris project",
        "osiris project summary",
    }

    if text in project_summary_phrases:
        return "dev_summary"

    if text == "cognition" or text.startswith("cognition "):
        return "cognition"

    if (
        text == "agent loop"
        or text.startswith("agent loop ")
        or text == "run agent"
        or text.startswith("run agent ")
    ):
        return "agent_loop"

    if (
        text == "self heal"
        or text.startswith("self heal ")
        or text == "self-heal"
        or text.startswith("self-heal ")
    ):
        return "self_heal"


    system_snapshot_phrases = {
        "system snapshot",
        "full system snapshot",
        "osiris system snapshot",
        "system report",
        "full system report",
        "osiris system report",
    }

    if text in system_snapshot_phrases:
        return "system_snapshot"

    document_summary_phrases = [
        "summarize the document",
        "summarise the document",
        "summary of the document",
        "summarize document",
        "summarise document",
        "what is the document about",
        "what was the document about",
        "tell me about the document",
        "explain the document",
        "explain this document",
    ]

    if any(phrase in text for phrase in document_summary_phrases):
        return "doc_query"

    return "chat"

def detect_command(message: str) -> str:
    text = message.lower().strip()
    priority_command = detect_priority_command(message)
    if priority_command != "chat":
        return priority_command


    project_summary_phrases = [
        "project summary",
        "dev summary",
        "development summary",
        "summarize project",
        "summarize the project",
        "summarize osiris project",
        "osiris project summary",
    ]

    if text in project_summary_phrases:
        return "dev_summary"


    if any(x in text for x in ["optimize my codebase", "analyze project", "inspect project", "analyze my codebase"]):
        return "cognition"

    security_phrases = [
        "security status",
        "is osiris secure",
        "is my system secure",
        "check security",
        "check exposed ports",
        "exposed ports",
        "outside threats",
    ]

    if any(phrase in text for phrase in security_phrases):
        return "security_status"

    system_phrases = [
        "how is my pc",
        "how is my computer",
        "check my system",
        "system status",
        "how is my tower",
        "how is osiris",
        "pc status",
        "tower status",
    ]

    ram_phrases = [
        "ram",
        "memory",
        "how much memory",
        "how much ram",
    ]

    gpu_phrases = [
        "gpu",
        "graphics card",
        "vram",
        "rtx",
        "nvidia",
    ]

    docker_phrases = [
        "docker",
        "containers",
        "container status",
        "what containers",
    ]

    if any(phrase in text for phrase in docker_phrases):
        return "docker_status"

    if any(phrase in text for phrase in gpu_phrases):
        return "gpu_status"

    if any(phrase in text for phrase in ram_phrases):
        return "system_status"

    if any(phrase in text for phrase in system_phrases):
        return "host_summary"

    dev_tree_phrases = [
        "project structure",
        "show my project",
        "show project tree",
        "project tree",
        "file structure",
        "show files",
    ]

    dev_summary_phrases = [
        "project summary",
        "summarize project",
        "what is in my project",
        "what files are in osiris",
    ]

    dev_search_phrases = [
        "find ",
        "search ",
        "where is ",
        "where are ",
    ]

    document_query_phrases = [
        "according to the document",
        "according to the pdf",
        "in the document",
        "in the pdf",
        "from the document",
        "from the pdf",
        "what did it say",
        "did you read it",
        "what does the book say",
        "what does the pdf say",
        "ask document ",
        "search document ",
    ]

    dev_read_phrases = [
        "read ",
        "open ",
        "show file ",
        "show me file ",
    ]

    if any(phrase in text for phrase in dev_tree_phrases):
        return "dev_tree"

    if any(phrase in text for phrase in dev_summary_phrases):
        return "dev_summary"

    if any(phrase in text for phrase in document_query_phrases):
        return "doc_query"

    if any(phrase in text for phrase in dev_read_phrases):
        return "dev_read"

    if any(phrase in text for phrase in dev_search_phrases):
        return "dev_search"

    review_patch_phrases = [
        "review and generate patch for ",
        "review and patch file ",
        "review and patch ",
        "generate review patch for ",
    ]

    if any(phrase in text for phrase in review_patch_phrases):
        return "dev_review_generate_patch"

    ai_patch_phrases = [
        "generate patch for ",
        "create patch for ",
        "make patch for ",
        "ai patch for ",
    ]

    if any(phrase in text for phrase in ai_patch_phrases):
        return "patch_generate_ai"

    review_file_phrases = [
        "review file ",
        "audit file ",
        "check file ",
    ]

    if any(phrase in text for phrase in review_file_phrases):
        return "dev_review_file"

    explain_file_phrases = [
        "explain file ",
        "summarize file ",
        "what does file ",
    ]

    if any(phrase in text for phrase in explain_file_phrases):
        return "dev_explain_file"

    rollback_phrases = [
        "show patch backups",
        "list patch backups",
        "show rollback backups",
        "list rollback backups",
        "show backups",
        "restore backup",
        "rollback backup",
    ]

    if any(phrase in text for phrase in rollback_phrases):
        if "restore backup" in text or "rollback backup" in text:
            return "patch_restore_request"
        return "patch_backups"

    patch_phrases = [
        "pending patches",
        "show patches",
        "show pending patches",
        "list patches",
        "view patch",
        "apply patch",
        "deny patch",
    ]

    if any(phrase in text for phrase in patch_phrases):
        if "apply patch" in text:
            return "patch_apply"
        if "deny patch" in text:
            return "patch_deny"
        if "view patch" in text:
            return "patch_view"
        return "patch_pending"

    return "chat"
