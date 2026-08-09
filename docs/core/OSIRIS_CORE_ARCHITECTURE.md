# OSIRIS Core Architecture

## Purpose

OSIRIS Core is the canonical runtime for the unified OSIRIS
intelligence.

OSIRIS is one identity and one intelligence system. Engineering,
software development, memory, household assistance, vision, voice,
devices, robotics, and future physical bodies are capabilities of
the same OSIRIS rather than separate products or personalities.

## Core primitives

### Identity

A stable OSIRIS identity shared by every interface, capability,
device, and physical body.

### Runtime

Owns the lifecycle and operational state of OSIRIS Core.

### Event Bus

Provides a single internal event vocabulary for communication among
core subsystems.

The initial implementation is process-local. Persistence and
distributed transport can later be added behind the same interface.

### Capability Registry

Every action available to OSIRIS must eventually be represented as
a capability.

Examples include:

- reasoning
- memory
- software tools
- development tools
- host administration
- cameras
- microphones
- sensors
- smart-home devices
- robot movement
- robotic manipulation

Capabilities declare availability, risk, and whether approval is
required.

### Task Manager

Provides a common lifecycle for OSIRIS work:

Created
-> Planning
-> Waiting Approval when required
-> Running
-> Verifying
-> Succeeded / Failed / Cancelled

Task persistence is intentionally deferred until the lifecycle model
has been validated.

## Migration strategy

Existing OSIRIS modules are not being discarded.

They will be migrated behind Core interfaces incrementally:

1. Core lifecycle
2. Capability registration
3. Existing model router
4. Existing intent classifier
5. Existing reasoner
6. Existing memory
7. Existing tool and command systems
8. Existing permissions and approvals
9. Existing devices and MQTT
10. Development and patch capabilities

The live API remains operational throughout the migration.

## Safety principle

Reasoning and physical execution are separate layers.

OSIRIS may decide what should be done, while deterministic execution
controllers and independent safety mechanisms enforce physical and
operational limits.

## Existing-system capability bootstrap

Phase 2B introduces discovery of existing OSIRIS subsystems.

Legacy modules are registered with Core without being rewritten or
executed during discovery.

A discovered subsystem begins in the `registered` state.

`registered` means:

- the implementation exists
- Core knows its identity
- Core knows its category
- Core knows its maximum risk classification
- Core knows whether approval is required

It does not yet mean the subsystem is safe for Core-directed
execution.

A subsystem becomes `available` only after a capability adapter and
its execution contract have been validated.

This distinction prevents OSIRIS from confusing code presence with
permission or operational readiness.
