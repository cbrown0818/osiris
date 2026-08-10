import os
import json
import uuid
from typing import Optional
import httpx
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from model_router import select_model
from api_auth import install_api_auth
from stackoverflow_retriever import search_stackoverflow
from osiris_core import core
from osiris_core.router import router as core_router

app = FastAPI(
    title="Osiris API",
    description="Local AI system backend for memory, agents, tools, and website integration.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://osiris.local",
        "http://api.osiris.local",
        "http://status.osiris.local",
        "http://192.168.4.120",
        "http://localhost:8088",
        "http://127.0.0.1:8088",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_api_auth(app)

app.include_router(core_router)

DATABASE_URL = os.getenv("DATABASE_URL")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
QDRANT_API_KEY = os.getenv("QDRANT__SERVICE__API_KEY")

MEMORY_COLLECTION = "lilith_memories"
EMBEDDING_MODEL = "nomic-embed-text"


class ChatRequest(BaseModel):
    message: str
    model: str = "auto"
    conversation_id: Optional[str] = None


class MemoryAddRequest(BaseModel):
    text: str
    source: str = "manual"
    importance: int = 5


class MemorySearchRequest(BaseModel):
    query: str
    limit: int = 5


class StackOverflowSearchRequest(BaseModel):
    query: str
    tags: list[str] = Field(
        default_factory=list
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=5,
    )


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_postgres():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id UUID PRIMARY KEY,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    importance INTEGER NOT NULL DEFAULT 5,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id UUID PRIMARY KEY,
                    conversation_id UUID NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
                ON chat_messages (conversation_id, created_at);
                """
            )
        conn.commit()


def get_qdrant_client():
    return QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
    )


def init_qdrant():
    client = get_qdrant_client()
    collections = client.get_collections().collections
    names = [collection.name for collection in collections]

    if MEMORY_COLLECTION not in names:
        client.create_collection(
            collection_name=MEMORY_COLLECTION,
            vectors_config=VectorParams(
                size=768,
                distance=Distance.COSINE,
            ),
        )


async def get_embedding(text: str):
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={
                "model": EMBEDDING_MODEL,
                "prompt": text,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]


@app.on_event("startup")
def startup():
    init_postgres()
    init_qdrant()
    core.start()


@app.on_event("shutdown")
def shutdown():
    core.stop()


@app.get("/")
def root():
    return {
        "system": "Osiris",
        "status": "online",
        "api": "running",
        "version": "0.2.0",
    }


@app.get("/health")
async def health():
    checks = {
        "api": "ok",
        "postgres": "unknown",
        "qdrant": "unknown",
        "ollama": "unknown",
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok;")
                cur.fetchone()
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "offline"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            qdrant_response = await client.get(
                f"{QDRANT_URL}/",
                headers={"api-key": QDRANT_API_KEY} if QDRANT_API_KEY else None,
            )
            checks["qdrant"] = "ok" if qdrant_response.status_code < 500 else "error"
        except Exception:
            checks["qdrant"] = "offline"

        try:
            ollama_response = await client.get(f"{OLLAMA_URL}/api/tags")
            checks["ollama"] = "ok" if ollama_response.status_code == 200 else "error"
        except Exception:
            checks["ollama"] = "offline"

    return checks


async def search_relevant_memories(query: str, limit: int = 5):
    try:
        embedding = await get_embedding(query)
        qdrant = get_qdrant_client()

        response = qdrant.query_points(
            collection_name=MEMORY_COLLECTION,
            query=embedding,
            limit=limit,
            with_payload=True,
        )

        memories = []
        for point in response.points:
            payload = point.payload or {}
            text = payload.get("text")
            if text:
                memories.append(
                    {
                        "id": str(point.id),
                        "score": point.score,
                        "text": text,
                        "source": payload.get("source", "unknown"),
                        "importance": payload.get("importance", 5),
                    }
                )

        return memories

    except Exception as exc:
        return [
            {
                "id": "memory_error",
                "score": 0,
                "text": f"Memory search failed: {exc}",
                "source": "system",
                "importance": 0,
            }
        ]


def save_chat_message(conversation_id: str, role: str, content: str, model: str | None = None):
    message_id = str(uuid.uuid4())

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (id, conversation_id, role, content, model)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (message_id, conversation_id, role, content, model),
            )
        conn.commit()

    return message_id


def get_recent_chat_messages(conversation_id: str, limit: int = 12):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, model, created_at
                FROM chat_messages
                WHERE conversation_id = %s
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()

    return list(reversed(rows))




@app.post("/knowledge/stackoverflow/search")
async def stackoverflow_search(
    request: StackOverflowSearchRequest,
):
    try:
        results = await search_stackoverflow(
            request.query,
            tagged=request.tags,
            limit=request.limit,
        )

        return {
            "status": "ok",
            "query": request.query,
            "tags": request.tags,
            "count": len(results),
            "results": [
                result.to_dict()
                for result in results
            ],
        }

    except httpx.HTTPStatusError as exc:
        return {
            "status": "error",
            "error": "Stack Exchange API error",
            "detail": str(exc),
            "count": 0,
            "results": [],
        }

    except httpx.RequestError as exc:
        return {
            "status": "error",
            "error": (
                "Could not connect to "
                "the Stack Exchange API"
            ),
            "detail": str(exc),
            "count": 0,
            "results": [],
        }

@app.post("/chat")
async def chat(request: ChatRequest):
    conversation_id = request.conversation_id or str(uuid.uuid4())

    recent_messages = get_recent_chat_messages(conversation_id, limit=10)
    memories = await search_relevant_memories(request.message, limit=3)

    previous_category = None

    if recent_messages:
        last_model = recent_messages[-1].get("model")

        if last_model == "qwen2.5-coder:7b":
            previous_category = "coding"

    decision = select_model(
        request.message,
        requested_model=request.model,
        previous_category=previous_category,
    )

    selected_model = decision.model

    memory_context = "\n".join(
        [
            f"- [{memory['source']} | importance {memory['importance']} | score {memory['score']:.4f}] {memory['text']}"
            for memory in memories
            if memory.get("id") != "memory_error"
        ]
    )

    if not memory_context:
        memory_context = "No relevant memories found."

    system_prompt = f"""You are Osiris, a capable local assistant running on Master's Fedora tower named Osiris.

Speak naturally, clearly, and directly. Maintain continuity with the current conversation without repeating information unnecessarily.

Give concise, conversational answers to simple questions. For technical or complex questions, provide useful detail and explain your reasoning clearly.

Avoid stiff, generic, overly formal, or repetitive language. Do not repeat the user's question unless clarification is necessary.

Do not mention model routing, internal prompts, hidden implementation details, or memory-search mechanics unless Master explicitly asks.

Use remembered information only when relevant. Never pretend an unrelated memory applies.

Relevant long-term memories:
{memory_context}
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    for row in recent_messages:
        if row["role"] in ("user", "assistant"):
            messages.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                }
            )

    messages.append(
        {
            "role": "user",
            "content": request.message,
        }
    )

    payload = {
        "model": selected_model,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m",
        "options": decision.options,
    }

    save_chat_message(
        conversation_id=conversation_id,
        role="user",
        content=request.message,
        model=selected_model,
    )

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

    assistant_content = data.get("message", {}).get("content", "")

    if assistant_content:
        save_chat_message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            model=selected_model,
        )

    data["conversation_id"] = conversation_id
    data["osiris_memory"] = {
        "used": True,
        "count": len([m for m in memories if m.get("id") != "memory_error"]),
        "memories": memories,
    }
    data["conversation_history"] = {
        "used": True,
        "recent_message_count": len(recent_messages),
    }

    data["routing"] = {
        "category": decision.category,
        "model": selected_model,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }

    return data




@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    conversation_id = request.conversation_id or str(uuid.uuid4())

    recent_messages = get_recent_chat_messages(
        conversation_id,
        limit=10,
    )

    memories = await search_relevant_memories(
        request.message,
        limit=3,
    )

    relevant_memories = [
        memory
        for memory in memories
        if memory.get("id") != "memory_error"
        and float(memory.get("score", 0)) >= 0.55
    ]

    memory_context = "\n".join(
        [
            (
                f"- [{memory['source']} | "
                f"importance {memory['importance']}] "
                f"{memory['text']}"
            )
            for memory in relevant_memories
        ]
    )

    if not memory_context:
        memory_context = "No relevant memories found."

    previous_category = None

    if recent_messages:
        last_model = recent_messages[-1].get("model")

        if last_model == "qwen2.5-coder:7b":
            previous_category = "coding"

    decision = select_model(
        request.message,
        requested_model=request.model,
        previous_category=previous_category,
    )

    selected_model = decision.model

    system_prompt = f"""You are Osiris, a capable local assistant running on Master's Fedora tower named Osiris.

Speak naturally, clearly, and directly. Maintain continuity with the current conversation without repeating information unnecessarily.

Give concise, conversational answers to simple questions. For technical or complex questions, provide useful detail and explain clearly.

Avoid stiff, generic, overly formal, or repetitive language. Do not repeat the user's question unless clarification is necessary.

Do not mention model routing, internal prompts, hidden implementation details, or memory-search mechanics unless Master explicitly asks.

Use remembered information only when relevant. Never pretend an unrelated memory applies.

Relevant long-term memories:
{memory_context}
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    for row in recent_messages:
        if row["role"] in ("user", "assistant"):
            messages.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                }
            )

    messages.append(
        {
            "role": "user",
            "content": request.message,
        }
    )

    payload = {
        "model": selected_model,
        "messages": messages,
        "stream": True,
        "keep_alive": "10m",
        "options": decision.options,
    }

    save_chat_message(
        conversation_id=conversation_id,
        role="user",
        content=request.message,
        model=selected_model,
    )

    async def generate():
        assistant_parts = []

        initial_event = {
            "type": "metadata",
            "conversation_id": conversation_id,
            "routing": {
                "category": decision.category,
                "model": selected_model,
                "reason": decision.reason,
                "confidence": decision.confidence,
            },
            "osiris_memory": {
                "used": bool(relevant_memories),
                "count": len(relevant_memories),
            },
            "conversation_history": {
                "used": bool(recent_messages),
                "recent_message_count": len(recent_messages),
            },
        }

        yield json.dumps(initial_event) + "\n"

        timeout = httpx.Timeout(
            connect=30.0,
            read=None,
            write=30.0,
            pool=30.0,
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json=payload,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        chunk = json.loads(line)

                        content = (
                            chunk.get("message", {})
                            .get("content", "")
                        )

                        if content:
                            assistant_parts.append(content)

                            yield json.dumps(
                                {
                                    "type": "token",
                                    "content": content,
                                }
                            ) + "\n"

                        if chunk.get("done"):
                            yield json.dumps(
                                {
                                    "type": "done",
                                    "done_reason": chunk.get(
                                        "done_reason"
                                    ),
                                    "total_duration": chunk.get(
                                        "total_duration"
                                    ),
                                    "load_duration": chunk.get(
                                        "load_duration"
                                    ),
                                    "prompt_eval_count": chunk.get(
                                        "prompt_eval_count"
                                    ),
                                    "eval_count": chunk.get(
                                        "eval_count"
                                    ),
                                    "eval_duration": chunk.get(
                                        "eval_duration"
                                    ),
                                }
                            ) + "\n"

            assistant_content = "".join(assistant_parts).strip()

            if assistant_content:
                save_chat_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_content,
                    model=selected_model,
                )

        except Exception as exc:
            yield json.dumps(
                {
                    "type": "error",
                    "message": (
                        f"{type(exc).__name__}: "
                        f"{str(exc) or 'streaming failed'}"
                    ),
                }
            ) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/chat/history/{conversation_id}")
def chat_history(conversation_id: str):
    messages = get_recent_chat_messages(conversation_id, limit=50)

    return {
        "conversation_id": conversation_id,
        "count": len(messages),
        "messages": messages,
    }


@app.get("/system/status")
async def system_status():
    status = {
        "system": "Osiris",
        "api": "ok",
        "postgres": {
            "status": "unknown",
            "memory_count": 0,
            "chat_message_count": 0,
            "conversation_count": 0,
        },
        "qdrant": {
            "status": "unknown",
            "collections": [],
        },
        "ollama": {
            "status": "unknown",
            "models": [],
        },
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS count FROM memories;")
                status["postgres"]["memory_count"] = cur.fetchone()["count"]

                cur.execute("SELECT COUNT(*) AS count FROM chat_messages;")
                status["postgres"]["chat_message_count"] = cur.fetchone()["count"]

                cur.execute("SELECT COUNT(DISTINCT conversation_id) AS count FROM chat_messages;")
                status["postgres"]["conversation_count"] = cur.fetchone()["count"]

        status["postgres"]["status"] = "ok"
    except Exception as exc:
        status["postgres"]["status"] = f"error: {exc}"

    try:
        qdrant = get_qdrant_client()
        collections = qdrant.get_collections().collections
        status["qdrant"]["collections"] = [collection.name for collection in collections]
        status["qdrant"]["status"] = "ok"
    except Exception as exc:
        status["qdrant"]["status"] = f"error: {exc}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            status["ollama"]["models"] = [
                {
                    "name": model.get("name"),
                    "size": model.get("size"),
                    "modified_at": model.get("modified_at"),
                }
                for model in data.get("models", [])
            ]
            status["ollama"]["status"] = "ok"
        except Exception as exc:
            status["ollama"]["status"] = f"error: {exc}"

    return status


@app.post("/memory/add")
async def add_memory(request: MemoryAddRequest):
    memory_id = str(uuid.uuid4())
    embedding = await get_embedding(request.text)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memories (id, text, source, importance)
                VALUES (%s, %s, %s, %s);
                """,
                (memory_id, request.text, request.source, request.importance),
            )
        conn.commit()

    qdrant = get_qdrant_client()
    qdrant.upsert(
        collection_name=MEMORY_COLLECTION,
        points=[
            PointStruct(
                id=memory_id,
                vector=embedding,
                payload={
                    "text": request.text,
                    "source": request.source,
                    "importance": request.importance,
                },
            )
        ],
    )

    return {
        "status": "stored",
        "id": memory_id,
        "text": request.text,
    }


@app.get("/memory/list")
def list_memories():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, text, source, importance, created_at
                FROM memories
                ORDER BY created_at DESC
                LIMIT 50;
                """
            )
            memories = cur.fetchall()

    return {
        "count": len(memories),
        "memories": memories,
    }


@app.post("/memory/search")
async def search_memory(request: MemorySearchRequest):
    embedding = await get_embedding(request.query)

    qdrant = get_qdrant_client()

    response = qdrant.query_points(
        collection_name=MEMORY_COLLECTION,
        query=embedding,
        limit=request.limit,
        with_payload=True,
    )

    return {
        "query": request.query,
        "results": [
            {
                "id": str(point.id),
                "score": point.score,
                "payload": point.payload,
            }
            for point in response.points
        ],
    }


# -------------------------------------------------------------------
# Osiris Permission Control
# -------------------------------------------------------------------

from fastapi import HTTPException
from permissions import load_permissions, check_tool, set_mode, update_tool


class PermissionModeUpdate(BaseModel):
    mode: str


class PermissionToolUpdate(BaseModel):
    tool_name: str
    enabled: Optional[bool] = None
    approval_required: Optional[bool] = None


@app.get("/permissions")
def get_permissions():
    try:
        return load_permissions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/permissions/check/{tool_name}")
def get_permission_check(tool_name: str):
    try:
        return check_tool(tool_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/permissions/mode")
def update_permission_mode(request: PermissionModeUpdate):
    try:
        return set_mode(request.mode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/permissions/tool")
def update_permission_tool(request: PermissionToolUpdate):
    try:
        return update_tool(
            tool_name=request.tool_name,
            enabled=request.enabled,
            approval_required=request.approval_required,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Tool Router
# -------------------------------------------------------------------

from tool_router import run_tool
from action_logger import read_recent_actions


class ToolRunRequest(BaseModel):
    tool_name: str
    params: dict = {}


@app.post("/tool/run")
def api_run_tool(request: ToolRunRequest):
    try:
        return run_tool(request.tool_name, request.params)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/actions/recent")
def api_recent_actions(limit: int = 50):
    try:
        return {
            "count": limit,
            "actions": read_recent_actions(limit),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Device Core
# -------------------------------------------------------------------

from device_core import load_devices, get_device, send_device_command, emergency_stop


class DeviceCommandRequest(BaseModel):
    tool_name: str
    capability: str
    action: str
    params: dict = {}


@app.get("/devices")
def api_list_devices():
    try:
        return load_devices()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/devices/{device_id}")
def api_get_device(device_id: str):
    try:
        return get_device(device_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/devices/{device_id}/command")
def api_device_command(device_id: str, request: DeviceCommandRequest):
    try:
        return send_device_command(
            device_id=device_id,
            tool_name=request.tool_name,
            capability=request.capability,
            action=request.action,
            params=request.params,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/robots/{device_id}/emergency-stop")
def api_robot_emergency_stop(device_id: str):
    try:
        return emergency_stop(device_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Device Event Listener
# -------------------------------------------------------------------

from mqtt_event_listener import start_device_event_listener, get_recent_device_events


@app.on_event("startup")
def startup_device_event_listener():
    start_device_event_listener()


@app.get("/devices/events/recent")
def api_recent_device_events(limit: int = 50):
    try:
        events = get_recent_device_events(limit)
        return {
            "count": len(events),
            "events": events,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Approval Core
# -------------------------------------------------------------------

from approvals import (
    init_approvals_table,
    create_approval,
    list_pending_approvals,
    get_approval,
    mark_approval_decision,
    decide_pending_approval,
)


@app.on_event("startup")
def startup_approval_core():
    init_approvals_table()


@app.get("/approvals/pending")
def api_pending_approvals(limit: int = 50):
    try:
        approvals = list_pending_approvals(limit)
        return {
            "count": len(approvals),
            "approvals": approvals,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/approvals/{approval_id}")
def api_get_approval(approval_id: str):
    approval = get_approval(approval_id)

    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    return approval


@app.post("/approvals/{approval_id}/deny")
def api_deny_approval(approval_id: str):
    try:
        return decide_pending_approval(
            approval_id=approval_id,
            status="denied",
            result={
                "message": "Denied by Master."
            },
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# -------------------------------------------------------------------
# Osiris Fedora Host Agent
# -------------------------------------------------------------------

from host_agent_client import (
    get_host_health,
    get_host_system_status,
    get_host_gpu_status,
    get_host_docker_status,
    get_host_summary,
)


@app.get("/host/health")
async def api_host_health():
    try:
        return await get_host_health()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/host/system")
async def api_host_system():
    try:
        return await get_host_system_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/host/gpu")
async def api_host_gpu():
    try:
        return await get_host_gpu_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/host/docker")
async def api_host_docker():
    try:
        return await get_host_docker_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/host/summary")
async def api_host_summary():
    try:
        return await get_host_summary()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Chat-to-Tool Router
# -------------------------------------------------------------------

from assistant_router import handle_assistant_command
from memory import get_recent_memories
from document_ingest import ingest_document, search_documents


class AssistantCommandRequest(BaseModel):
    message: str


@app.post("/assistant/command")
async def api_assistant_command(request: AssistantCommandRequest):
    try:
        return await handle_assistant_command(request.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Approval Execute
# -------------------------------------------------------------------

from device_core import send_device_command


@app.post("/approvals/{approval_id}/approve")
async def api_approve_approval(
    approval_id: str,
):
    try:
        approval = get_approval(
            approval_id
        )

        if not approval:
            raise HTTPException(
                status_code=404,
                detail="Approval not found",
            )

        tool_name = approval["tool_name"]
        params = approval.get("params") or {}
        permission = (
            approval.get("permission")
            or {}
        )
        action = approval.get("action")

        is_core_approval = (
            action == "core.capability.execute"
            and permission.get(
                "authorization_layer"
            ) == "osiris_core"
        )

        # --------------------------------------------------
        # OSIRIS Core capability approval
        # --------------------------------------------------

        if is_core_approval:
            if approval["status"] == "pending":
                decide_pending_approval(
                    approval_id=approval_id,
                    status="approved",
                    result={
                        "message": (
                            "Approved for one exact "
                            "Core execution."
                        )
                    },
                )

            elif approval["status"] != "approved":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Approval is not pending. "
                        "Current status: "
                        f"{approval['status']}"
                    ),
                )

            payload = params.get(
                "payload",
                {},
            )

            if not isinstance(
                payload,
                dict,
            ):
                mark_approval_decision(
                    approval_id=approval_id,
                    status="failed",
                    result={
                        "error": (
                            "Core approval payload "
                            "is invalid."
                        )
                    },
                )

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Core approval payload "
                        "must be an object."
                    ),
                )

            capability_result = (
                await core.adapters.execute(
                    tool_name,
                    payload,
                    approval_id=approval_id,
                )
            )

            updated = get_approval(
                approval_id
            )

            if not capability_result.success:
                if (
                    updated
                    and updated.get("status")
                    == "approved"
                ):
                    mark_approval_decision(
                        approval_id=approval_id,
                        status="failed",
                        result={
                            "error": (
                                capability_result.error
                                or {}
                            )
                        },
                    )

                    updated = get_approval(
                        approval_id
                    )

                return {
                    "status": (
                        updated.get("status")
                        if updated
                        else "failed"
                    ),
                    "approval": updated,
                    "execution_result": (
                        capability_result.as_dict()
                    ),
                }

            return {
                "status": "executed",
                "approval": updated,
                "execution_result": (
                    capability_result.as_dict()
                ),
            }

        # --------------------------------------------------
        # Existing device command approval execution
        # --------------------------------------------------

        if approval["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Approval is not pending. "
                    "Current status: "
                    f"{approval['status']}"
                ),
            )

        if (
            "device_id" in params
            and "capability" in params
            and "action" in params
        ):
            decide_pending_approval(
                approval_id=approval_id,
                status="approved",
                result={
                    "message": (
                        "Approved for device execution."
                    )
                },
            )

            result = send_device_command(
                device_id=params["device_id"],
                tool_name=tool_name,
                capability=params["capability"],
                action=params["action"],
                params=params.get(
                    "params",
                    {},
                ),
                force_approved=True,
            )

            updated = mark_approval_decision(
                approval_id=approval_id,
                status="executed",
                result=result,
            )

            return {
                "status": "executed",
                "approval": updated,
                "execution_result": result,
            }

        # --------------------------------------------------
        # Existing approval types without an execution
        # handler retain approval-only behavior.
        # --------------------------------------------------

        updated = decide_pending_approval(
            approval_id=approval_id,
            status="approved",
            result={
                "message": (
                    "Approved, but no executable "
                    "handler exists yet for this "
                    "approval type."
                )
            },
        )

        return {
            "status": "approved",
            "approval": updated,
        }

    except HTTPException:
        raise

    except Exception as exc:
        try:
            current = get_approval(
                approval_id
            )

            if (
                current
                and current.get("status")
                in {
                    "approved",
                    "executing",
                }
            ):
                mark_approval_decision(
                    approval_id=approval_id,
                    status="failed",
                    result={
                        "error": str(exc)
                    },
                )

        except Exception:
            pass

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# -------------------------------------------------------------------
# Osiris Dev Core
# -------------------------------------------------------------------

from dev_core import (
    list_tree,
    read_file,
    search_project,
    project_summary,
    DevCoreError,
)


class DevSearchRequest(BaseModel):
    query: str
    max_results: int = 50


@app.get("/dev/project/summary")
def api_dev_project_summary():
    try:
        return project_summary()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/dev/tree")
def api_dev_tree(max_depth: int = 4):
    try:
        return list_tree(max_depth=max_depth)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/dev/file")
def api_dev_file(path: str, max_bytes: int = 120000):
    try:
        return read_file(path, max_bytes=max_bytes)
    except DevCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/dev/search")
def api_dev_search(request: DevSearchRequest):
    try:
        return search_project(
            query=request.query,
            max_results=request.max_results,
        )
    except DevCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Patch Preview Core
# -------------------------------------------------------------------

from patch_core import (
    init_patches_table,
    create_patch,
    list_pending_patches,
    get_patch,
    deny_patch,
)


class PatchCreateRequest(BaseModel):
    file_path: str
    proposed_content: str
    reason: str | None = None


@app.on_event("startup")
def startup_patch_core():
    init_patches_table()


@app.post("/patches/create")
def api_create_patch(request: PatchCreateRequest):
    try:
        patch = create_patch(
            file_path=request.file_path,
            proposed_content=request.proposed_content,
            reason=request.reason,
        )

        return {
            "status": "pending",
            "patch": patch,
        }

    except DevCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/patches/pending")
def api_pending_patches(limit: int = 50):
    try:
        patches = list_pending_patches(limit)
        return {
            "count": len(patches),
            "patches": patches,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/patches/{patch_id}")
def api_get_patch(patch_id: str):
    patch = get_patch(patch_id)

    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    return patch


@app.post("/patches/{patch_id}/deny")
def api_deny_patch(patch_id: str):
    try:
        return deny_patch(patch_id)
    except DevCoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Patch Apply Core
# -------------------------------------------------------------------

from patch_core import apply_patch


@app.post("/patches/{patch_id}/apply")
def api_apply_patch(patch_id: str):
    try:
        patch = get_patch(patch_id)

        if not patch:
            raise HTTPException(status_code=404, detail="Patch not found.")

        file_path = patch.get("file_path", "")

        service_impacting = (
            file_path == "docker-compose.yml"
            or file_path == "host-agent/host_agent.py"
            or file_path.startswith("osiris-api/app/")
            or file_path.startswith("host-agent/")
        )

        if service_impacting:
            approval = create_approval(
                tool_name="patch_apply",
                target=file_path,
                action="apply_patch",
                params={
                    "patch_id": patch_id,
                    "file_path": file_path,
                },
                permission={
                    "allowed": True,
                    "approval_required": True,
                    "risk": "high",
                    "category": "development",
                    "reason": "Applying this patch may affect a running Osiris service and requires approval.",
                },
            )

            return {
                "status": "approval_required",
                "approval_id": approval["id"],
                "approval": approval,
                "message": "This patch affects a service file and requires approval before apply.",
            }

        return apply_patch(patch_id)

    except DevCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris AI Patch Generator
# -------------------------------------------------------------------

from patch_core import generate_patch_with_ai


class PatchGenerateRequest(BaseModel):
    file_path: str
    instruction: str
    model: str = "qwen2.5-coder:7b"


@app.post("/patches/generate")
async def api_generate_patch(request: PatchGenerateRequest):
    try:
        return await generate_patch_with_ai(
            file_path=request.file_path,
            instruction=request.instruction,
            model=request.model,
        )
    except DevCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Security Status
# -------------------------------------------------------------------

from host_agent_client import get_host_security_status


@app.get("/security/status")
async def api_security_status():
    try:
        return await get_host_security_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Patch Rollback Core
# -------------------------------------------------------------------

from patch_core import list_patch_backups, restore_patch_backup


class PatchRestoreRequest(BaseModel):
    backup_path: str


@app.get("/backups/patches")
def api_list_patch_backups():
    try:
        backups = list_patch_backups()
        return {
            "count": len(backups),
            "backups": backups,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/backups/restore")
def api_restore_patch_backup(request: PatchRestoreRequest):
    try:
        approval = create_approval(
            tool_name="patch_rollback",
            target=request.backup_path,
            action="restore_patch_backup",
            params={
                "backup_path": request.backup_path,
            },
            permission={
                "allowed": True,
                "approval_required": True,
                "risk": "high",
                "category": "development",
                "reason": "Restoring a patch backup modifies project files and requires approval.",
            },
        )

        return {
            "status": "approval_required",
            "approval_id": approval["id"],
            "approval": approval,
            "message": "Rollback restore requires approval before it is applied.",
        }

    except DevCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Patch Rollback Core
# -------------------------------------------------------------------

from patch_core import list_patch_backups, restore_patch_backup


class PatchRestoreRequest(BaseModel):
    backup_path: str


@app.get("/backups/patches")
def api_list_patch_backups():
    try:
        backups = list_patch_backups()
        return {
            "count": len(backups),
            "backups": backups,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/backups/restore")
def api_restore_patch_backup(request: PatchRestoreRequest):
    try:
        return restore_patch_backup(request.backup_path)
    except DevCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# -------------------------------------------------------------------
# Osiris Audit Log Core
# -------------------------------------------------------------------

from action_logger import read_recent_actions


@app.get("/audit/events")
def api_audit_events(limit: int = 100):
    try:
        limit = max(1, min(limit, 500))
        events = read_recent_actions(limit=limit)
        return {
            "count": len(events),
            "events": events,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/memory/recent")
async def recent_memory(limit: int = 25):
    try:
        memories = await get_recent_memories(limit)
        return {
            "status": "ok",
            "count": len(memories),
            "memories": memories,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


@app.post("/documents/ingest")
async def documents_ingest(path: str):
    try:
        result = await ingest_document(path)
        return {
            "status": "ok",
            "result": result,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


@app.get("/documents/search")
async def documents_search(q: str, limit: int = 10):
    try:
        result = await search_documents(q, limit)
        return {
            "status": "ok",
            "result": result,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

