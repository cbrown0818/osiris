from fastapi import APIRouter, Query

from .runtime import core


router = APIRouter(
    prefix="/core",
    tags=["core"],
)


@router.get("/status")
def core_status():
    return core.status()


@router.get("/identity")
def core_identity():
    return core.identity.as_dict()


@router.get("/capabilities")
def core_capabilities():
    return {
        "count": core.capabilities.count,
        "capabilities": [
            capability.as_dict()
            for capability in core.capabilities.all()
        ],
    }


@router.get("/events")
def core_events(
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
):
    events = core.events.recent(limit)

    return {
        "count": len(events),
        "events": [
            event.as_dict()
            for event in events
        ],
    }


@router.get("/tasks")
def core_tasks():
    tasks = core.tasks.all()

    return {
        "count": len(tasks),
        "tasks": [
            task.as_dict()
            for task in tasks
        ],
    }
