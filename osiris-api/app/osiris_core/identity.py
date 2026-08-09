from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class OsirisIdentity:
    """
    Stable identity for the unified OSIRIS intelligence.

    This represents one OSIRIS identity regardless of which
    workstation, edge device, robot, interface, or capability
    is being used.
    """

    identifier: str = "osiris"
    name: str = "OSIRIS"
    system_type: str = "general_intelligence_operating_system"
    motto: str = "Intelligence for Life."
    core_version: str = "0.1.0"
    foundation_version: str = "0.3.0"

    def as_dict(self) -> dict[str, str]:
        return asdict(self)
