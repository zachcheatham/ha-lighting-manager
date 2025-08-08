# Lighting Manager - Implementation Plan v4.0: The Unified Architecture

## 1. Vision & Guiding Principles

This document defines the modernization strategy for the `lighting_manager` integration to target Home Assistant 2025.7 and Core 16.0. The plan is based on current Home Assistant developer guidance that states "Config entries are configuration data that are persistently stored by Home Assistant. A config entry is created by a user via the UI. The UI flow is powered by a config flow handler as defined by the integration." [Source](https://developers.home-assistant.io/docs/config_entries_index).

The architecture elevates lighting **layers** to first-class entities. All state that influences lighting decisions will be stored in these layer entities, ensuring:

- **Architectural Purity** – No hidden state; all decisions derive from entity states.
- **Total Observability** – Users can inspect layer and sensor entities to understand behaviour.
- **Reactive, Event-Driven Design** – Updates occur in response to entity state changes.
- **Single Source of Truth** – Layer entities hold the authoritative state.
- **Calculate → Store → Apply** – A clear pipeline for determining light output.

## 2. Target File Structure

```
custom_components/lighting_manager/
├── __init__.py
├── manifest.json
├── config_flow.py
├── coordinator.py
├── const.py
├── layer.py
├── sensor.py
├── services.yaml
└── translations/
    └── en.json
```

## 3. Phased Implementation Plan

### Phase 1: Layer Entities and Zone Onboarding
1. **Project Scaffolding**
   - Ensure `manifest.json` declares the domain, version `4.0.0`, `config_flow: true`, and `iot_class: local_push`.
   - Create `const.py` with `DOMAIN`, service names, platform list, and default layer definitions.
2. **Config Flow**
   - `config_flow.py` collects `zone_name` and `light_entities` and creates a config entry.
3. **Layer Platform**
   - Implement `layer.py` with `LayerEntity` inheriting from `RestoreEntity`.
   - `async_setup_entry` creates default layers (`base`, `holiday`, `alert`, etc.) following `layer.{zone}_{layer}` naming.

### Phase 2: Calculation Engine and Control
1. **ZoneCoordinator**
   - Located in `coordinator.py`, inherit from `DataUpdateCoordinator` and watch only its zone's layer entities.
   - `_async_update_data` collects layer states and delegates to `LightingManager.calculate_zone_state`.
2. **LightingManager Core**
   - Remove internal state storage; compute results directly from entity states.
   - `calculate_zone_state` resolves priorities, force, and lock flags to produce the final light state.
3. **Apply Step**
   - After coordinator refresh, apply the final state to target lights via `light.turn_on`.

### Phase 3: Services and Events
1. **Service Definitions**
   - Modernize `services.yaml` with selectors and target `lighting_manager` entities.
   - Register `activate_layer` and `deactivate_layer` handlers in `__init__.py`.
2. **Event Emission**
   - Coordinator fires events (`lighting_manager.layer_applied`, etc.) after each calculation to aid debugging.

### Phase 4: Observability
1. **Sensor Platform**
   - `sensor.py` creates coordinator-based sensors exposing winning layer, adaptive factors, and conflict data.
2. **Device Registry Integration**
   - Layers and sensors share a parent device representing the zone, grouping entities neatly in the UI.

## 4. Next Steps

- Implement Phase 1 to bootstrap the new entity model.
- Iterate through Phases 2–4, ensuring each step maintains the Calculate → Store → Apply pipeline.

