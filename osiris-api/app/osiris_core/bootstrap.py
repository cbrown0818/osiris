from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.util import find_spec

from .capabilities import (
    Capability,
    CapabilityRegistry,
    CapabilityRisk,
    CapabilityState,
)


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    capability_id: str
    name: str
    description: str
    category: str
    module: str
    risk: CapabilityRisk
    requires_approval: bool = False


@dataclass(frozen=True, slots=True)
class BootstrapReport:
    total_specs: int
    present: int
    missing: int
    newly_registered: int
    already_registered: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


EXISTING_CAPABILITY_SPECS = (
    CapabilitySpec(
        capability_id="intelligence.model_routing",
        name="Model Routing",
        description=(
            "Select the appropriate local AI model "
            "for a request."
        ),
        category="intelligence",
        module="model_router",
        risk=CapabilityRisk.READ_ONLY,
    ),
    CapabilitySpec(
        capability_id="intelligence.intent",
        name="Intent Classification",
        description=(
            "Determine the intent and handling path "
            "for a request."
        ),
        category="intelligence",
        module="intent_classifier",
        risk=CapabilityRisk.READ_ONLY,
    ),
    CapabilitySpec(
        capability_id="intelligence.reasoning",
        name="Reasoning",
        description=(
            "Perform structured reasoning over "
            "OSIRIS requests and context."
        ),
        category="intelligence",
        module="reasoner",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="intelligence.cognition",
        name="Cognition Execution",
        description=(
            "Coordinate higher-level cognition "
            "and reasoning execution."
        ),
        category="intelligence",
        module="cognition_executor",
        risk=CapabilityRisk.MODERATE,
    ),
    CapabilitySpec(
        capability_id="intelligence.assistant_routing",
        name="Assistant Routing",
        description=(
            "Route assistant requests through "
            "existing OSIRIS handling paths."
        ),
        category="intelligence",
        module="assistant_router",
        risk=CapabilityRisk.LOW,
    ),
    CapabilitySpec(
        capability_id="intelligence.model_orchestration",
        name="Model Orchestration",
        description=(
            "Coordinate model selection and "
            "model-oriented execution."
        ),
        category="intelligence",
        module="model_orchestrator",
        risk=CapabilityRisk.LOW,
    ),
    CapabilitySpec(
        capability_id="memory.semantic",
        name="Semantic Memory",
        description=(
            "Use the existing OSIRIS memory subsystem."
        ),
        category="memory",
        module="memory",
        risk=CapabilityRisk.MODERATE,
    ),
    CapabilitySpec(
        capability_id="tools.execution",
        name="Tool Execution",
        description=(
            "Execute registered OSIRIS software tools."
        ),
        category="tools",
        module="tool_router",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="tools.command_detection",
        name="Command Detection",
        description=(
            "Recognize deterministic OSIRIS commands."
        ),
        category="tools",
        module="command_detector",
        risk=CapabilityRisk.READ_ONLY,
    ),
    CapabilitySpec(
        capability_id="security.permissions",
        name="Permissions",
        description=(
            "Evaluate and modify OSIRIS capability "
            "permissions."
        ),
        category="security",
        module="permissions",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="security.approvals",
        name="Approvals",
        description=(
            "Manage approval-gated OSIRIS actions."
        ),
        category="security",
        module="approvals",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="devices.control",
        name="Device Control",
        description=(
            "Interact with registered OSIRIS devices."
        ),
        category="devices",
        module="device_core",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="devices.mqtt_bridge",
        name="MQTT Device Bridge",
        description=(
            "Publish OSIRIS device commands through MQTT."
        ),
        category="devices",
        module="mqtt_bridge",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="devices.mqtt_events",
        name="MQTT Event Listener",
        description=(
            "Receive device and sensor events over MQTT."
        ),
        category="devices",
        module="mqtt_event_listener",
        risk=CapabilityRisk.READ_ONLY,
    ),
    CapabilitySpec(
        capability_id="host.agent",
        name="Host Agent",
        description=(
            "Interact with the OSIRIS host-agent service."
        ),
        category="host",
        module="host_agent_client",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="documents.knowledge",
        name="Document Knowledge",
        description=(
            "Ingest and retrieve knowledge from documents."
        ),
        category="knowledge",
        module="document_ingest",
        risk=CapabilityRisk.MODERATE,
    ),
    CapabilitySpec(
        capability_id="development.core",
        name="Development Core",
        description=(
            "Inspect and operate on OSIRIS development "
            "projects."
        ),
        category="development",
        module="dev_core",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="development.patching",
        name="Patch Management",
        description=(
            "Create, review, and apply OSIRIS code patches."
        ),
        category="development",
        module="patch_core",
        risk=CapabilityRisk.HIGH,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="recovery.self_heal",
        name="Self Healing",
        description=(
            "Use controlled OSIRIS self-healing routines."
        ),
        category="recovery",
        module="self_heal",
        risk=CapabilityRisk.CRITICAL,
        requires_approval=True,
    ),
    CapabilitySpec(
        capability_id="system.monitoring",
        name="System Monitoring",
        description=(
            "Inspect OSIRIS runtime and host health."
        ),
        category="system",
        module="system_monitor",
        risk=CapabilityRisk.READ_ONLY,
    ),
    CapabilitySpec(
        capability_id="knowledge.stackoverflow",
        name="Stack Overflow Retrieval",
        description=(
            "Retrieve programming knowledge through "
            "the existing Stack Overflow retriever."
        ),
        category="knowledge",
        module="stackoverflow_retriever",
        risk=CapabilityRisk.READ_ONLY,
    ),
)


def _module_present(module_name: str) -> bool:
    try:
        return find_spec(module_name) is not None
    except (
        ImportError,
        AttributeError,
        ValueError,
    ):
        return False


def bootstrap_existing_capabilities(
    registry: CapabilityRegistry,
) -> BootstrapReport:
    present = 0
    missing = 0
    newly_registered = 0
    already_registered = 0

    for spec in EXISTING_CAPABILITY_SPECS:
        if registry.get(spec.capability_id) is not None:
            already_registered += 1

            if _module_present(spec.module):
                present += 1
            else:
                missing += 1

            continue

        discovered = _module_present(spec.module)

        if discovered:
            present += 1
            state = CapabilityState.REGISTERED
            migration_state = "legacy_present"
        else:
            missing += 1
            state = CapabilityState.UNAVAILABLE
            migration_state = "module_missing"

        registry.register(
            Capability(
                capability_id=spec.capability_id,
                name=spec.name,
                description=spec.description,
                state=state,
                risk=spec.risk,
                requires_approval=spec.requires_approval,
                metadata={
                    "category": spec.category,
                    "module": spec.module,
                    "discovered": discovered,
                    "migration_state": migration_state,
                },
            )
        )

        newly_registered += 1

    return BootstrapReport(
        total_specs=len(EXISTING_CAPABILITY_SPECS),
        present=present,
        missing=missing,
        newly_registered=newly_registered,
        already_registered=already_registered,
    )
