from typing import Literal

TaskType = Literal[
    "chat",
    "reasoning",
    "intent",
    "code_review",
    "code_patch",
    "document_answer",
    "embedding",
]

MODEL_MAP = {
    "chat": "dolphin3:8b",
    "reasoning": "llama3.1:8b",
    "intent": "llama3.1:8b",
    "code_review": "qwen2.5-coder:7b",
    "code_patch": "qwen2.5-coder:7b",
    "document_answer": "llama3.1:8b",
    "embedding": "nomic-embed-text:latest",
}

def choose_model(task: TaskType | str) -> str:
    return MODEL_MAP.get(task, "llama3.1:8b")
