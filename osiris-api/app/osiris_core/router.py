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
    capabilities = core.capabilities.all()

    by_state: dict[str, int] = {}
    by_category: dict[str, int] = {}

    for capability in capabilities:
        state = capability.state.value

        by_state[state] = (
            by_state.get(state, 0) + 1
        )

        category = capability.metadata.get(
            "category",
            "core",
        )

        by_category[category] = (
            by_category.get(category, 0) + 1
        )

    return {
        "count": len(capabilities),
        "by_state": by_state,
        "by_category": by_category,
        "capabilities": [
            capability.as_dict()
            for capability in capabilities
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
