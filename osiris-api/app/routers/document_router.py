from typing import Any

import httpx

from document_ingest import (
    search_documents,
    get_latest_document,
    get_document_intro_chunks,
)


async def handle_document_query(message: str) -> dict[str, Any]:
    command = "doc_query"
    query = message.strip()

    cleanup_prefixes = [
        "ask document ",
        "search document ",
        "according to the document ",
        "according to the pdf ",
        "in the document ",
        "in the pdf ",
        "from the document ",
        "from the pdf ",
    ]

    lowered = query.lower()
    for prefix in cleanup_prefixes:
        if lowered.startswith(prefix):
            query = query[len(prefix):].strip()
            break

    latest_doc = None
    if query.lower() in {
        "did you read it",
        "what did it say",
        "what does it say",
        "what does the pdf say",
        "what does the book say",
        "summarize it",
        "summarize the document",
        "summarize the pdf",
    }:
        latest_doc = await get_latest_document()
        query = "summary main topics key ideas"


    try:
        if latest_doc:
            intro_data = await get_document_intro_chunks(latest_doc.get("source_path"), limit=6)
            semantic_data = await search_documents(
                query="main topics practical programming python software development tools testing debugging packages",
                limit=6,
            )

            data = {
                "query": "hybrid_document_summary",
                "count": len(intro_data.get("results", [])) + len(semantic_data.get("results", [])),
                "mode": "latest_document_intro_plus_semantic",
                "results": intro_data.get("results", []) + semantic_data.get("results", []),
            }
        else:
            data = await search_documents(query=query, limit=5)
    except Exception as exc:
        return {
            "type": "tool_result",
            "command": command,
            "answer": f"I could not search document memory: {type(exc).__name__}: {str(exc)}",
            "data": {
                "query": query,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        }

    results = data.get("results", [])

    if not results:
        return {
            "type": "tool_result",
            "command": command,
            "answer": "I searched document memory, but found no relevant matches.",
            "data": data,
        }

    context_parts = []
    for item in results:
        context_parts.append(
            f"Source: {item.get('source_path')} | chunk {item.get('chunk_index')} | score {item.get('score')}\n"
            f"{item.get('preview')}"
        )

    context = "\n\n---\n\n".join(context_parts)

    latest_doc_text = ""
    if latest_doc:
        latest_doc_text = (
            f"Most recent ingested document: {latest_doc.get('source_path')} "
            f"with {latest_doc.get('chunks')} chunks.\n\n"
        )

    prompt = (
        "You are Osiris, answering using retrieved document memory.\n\n"
        f"{latest_doc_text}"
        "Answer the user's question using ONLY the retrieved document context. "
        "Be clear, practical, and concise. If the context is partial, say what can be inferred from it.\n\n"
        f"User question: {message}\n\n"
        "Retrieved context:\n"
        "-----BEGIN CONTEXT-----\n"
        f"{context}\n"
        "-----END CONTEXT-----\n"
    )

    ollama_url = "http://ollama:11434"

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": "llama3.1:8b",
                    "messages": [
                        {
                            "role": "system",
                            "content": """
You are Osiris.

You have already read and processed the document provided by the user.

The retrieved context below comes directly from your internal document memory.

Never say:
- I did not read it
- I cannot read documents
- I have not seen the document

You HAVE already read and processed the document.

Answer confidently using the retrieved document context as your knowledge source.

If asked to summarize, summarize the document.
If asked questions, answer from document memory.
""",
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
            llm_data = response.json()
    except Exception as exc:
        previews = "\n\n".join(
            f"- {item.get('source_path')} chunk {item.get('chunk_index')}: {item.get('preview')[:500]}"
            for item in results
        )
        return {
            "type": "tool_result",
            "command": command,
            "answer": "I found relevant document memory, but failed to summarize it with Ollama. Raw matches:\n\n" + previews,
            "data": {
                "search": data,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        }

    answer = llm_data.get("message", {}).get("content", "").strip()

    if not answer:
        answer = "I found relevant document memory, but the model returned no answer."

    return {
        "type": "tool_result",
        "command": command,
        "answer": answer,
        "data": {
            "query": query,
            "search": data,
            "model": "llama3.1:8b",
        },
    }
