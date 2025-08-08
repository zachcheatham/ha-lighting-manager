# Lighting Manager Requirements Specification 

## Executive Summary

The Lighting Manager is a Home Assistant integration that implements a sophisticated layer-based lighting control system. It replaces chaotic automation sprawl with a clean, priority-based state orchestration engine where every lighting decision is observable, debuggable, and predictable.

## Core Architectural Requirements

### 1. Layer-Based Priority System

#### 1.1 Layer Entity Platform
- **REQ-L001**: Create a new Home Assistant entity domain called `layer`
- **REQ-L002**: Each layer entity must be a pure state container with NO control logic
- **REQ-L003**: Layer entities must be first-class citizens visible in the UI
- **REQ-L004**: Each layer must have the following immutable properties:
  - `zone_id`: String identifier for the zone (e.g., "living_room")
  - `layer_id`: String identifier for the layer type (e.g., "environmental")
  - `priority`: Integer 0-100, higher wins in conflicts
  - `entity_id`: Must follow pattern `layer.{zone_id}_{layer_id}`

#### 1.2 Layer State Properties
- **REQ-L005**: Each layer must maintain the following mutable state:
  - `active`: Boolean indicating if layer is participating in calculations
  - `brightness`: Optional integer 0-255 or None for no brightness control
  - `color_temp`: Optional mireds value or None for no color temp control
  - `rgb_color`: Optional tuple (r,g,b) or None for no color control
  - `transition`: Optional float seconds for state changes
  - `force`: Boolean to force this layer regardless of priority
  - `locked`: Boolean to prevent any changes to this layer
  - `conditions`: Dict of conditions that must be met for layer activation
  - `last_updated`: DateTime of last state change
  - `source`: String identifier of what triggered the state (e.g., "automation.movie_mode")

#### 1.3 Standard Layer Types
- **REQ-L006**: Every zone must have these standard layers created automatically:
  - `base_adaptive` (priority 0): Circadian rhythm baseline
  - `environmental` (priority 10): Weather/sensor adjustments
  - `activity` (priority 20): Motion/presence-based changes
  - `mode` (priority 30): Scene/mode overrides (movie, dinner, etc.)
  - `manual` (priority 100): User manual control

#### 1.4 Layer Persistence
- **REQ-L007**: Layer states must persist across restarts using RestoreEntity
- **REQ-L008**: Layer configuration must be stored in config entries, not YAML

### 2. Orchestration Engine

#### 2.1 Core Pattern
- **REQ-O001**: Implement Calculate → Store → Apply pattern for all state changes
- **REQ-O002**: Each zone must have exactly ONE orchestration engine instance
- **REQ-O003**: Orchestration must be triggered by layer state changes via events
- **REQ-O004**: All calculations must be debounced (100ms) to prevent race conditions

#### 2.2 State Calculation
- **REQ-O005**: Calculator must be pure functions with no side effects
- **REQ-O006**: Priority resolution: Highest priority active layer wins
- **REQ-O007**: Force flag overrides normal priority calculations
- **REQ-O008**: Locked layers cannot be modified by any calculation
- **REQ-O009**: Support layer merging for compatible properties (future)

#### 2.3 Conflict Detection
- **REQ-O010**: Detect and report priority ties
- **REQ-O011**: Detect and report conflicting force flags
- **REQ-O012**: Log all conflicts with resolution strategy used
- **REQ-O013**: Fire events for conflicts that require user intervention

#### 2.4 State Application
- **REQ-O014**: Apply calculated state to all zone lights atomically
- **REQ-O015**: Support transition times for smooth changes
- **REQ-O016**: Handle unavailable lights gracefully
- **REQ-O017**: Respect light capabilities (some don't support color temp)

### 3. Observable State

#### 3.1 Calculation Sensors
- **REQ-S001**: Create sensor showing current winning layer per zone
- **REQ-S002**: Create sensor showing calculation path (layer evaluation order)
- **REQ-S003**: Create sensor showing last calculation timestamp
- **REQ-S004**: Create sensor showing conflict status and details

#### 3.2 Debug Sensors
- **REQ-S005**: Create sensor showing full calculation input (all active layers)
- **REQ-S006**: Create sensor showing full calculation output (final state)
- **REQ-S007**: Create sensor showing performance metrics (calculation time)

#### 3.3 Events
- **REQ-S008**: Fire event when layer activated: `lighting_manager.layer_activated`
- **REQ-S009**: Fire event when layer deactivated: `lighting_manager.layer_deactivated`
- **REQ-S010**: Fire event after calculation: `lighting_manager.calculation_complete`
- **REQ-S011**: Fire event on conflicts: `lighting_manager.conflict_detected`
- **REQ-S012**: Fire event on state applied: `lighting_manager.state_applied`

### 4. Service API

#### 4.1 Layer Control Services
- **REQ-A001**: `lighting_manager.activate_layer`
  - Target: layer entity
  - Fields: brightness, color_temp, rgb_color, transition, source
- **REQ-A002**: `lighting_manager.deactivate_layer`
  - Target: layer entity
- **REQ-A003**: `lighting_manager.update_layer`
  - Target: layer entity
  - Fields: All mutable state properties
- **REQ-A004**: `lighting_manager.set_layer_priority`
  - Target: layer entity
  - Fields: priority (0-100)

#### 4.2 Layer State Services
- **REQ-A005**: `lighting_manager.lock_layer`
  - Target: layer entity
  - Prevents all modifications
- **REQ-A006**: `lighting_manager.unlock_layer`
  - Target: layer entity
- **REQ-A007**: `lighting_manager.force_layer`
  - Target: layer entity
  - Makes layer apply regardless of priority

#### 4.3 Zone Control Services
- **REQ-A008**: `lighting_manager.recalculate_zone`
  - Fields: zone_id
  - Forces immediate recalculation
- **REQ-A009**: `lighting_manager.reset_zone`
  - Fields: zone_id
  - Deactivates all layers except base

#### 4.4 Advanced Services
- **REQ-A010**: `lighting_manager.create_dynamic_layer`
  - Fields: zone_id, layer_id, priority
  - Creates temporary layers for special events
- **REQ-A011**: `lighting_manager.apply_preset`
  - Fields: zone_id, preset_name
  - Configures multiple layers atomically

### 5. Configuration & Setup

#### 5.1 Config Flow
- **REQ-C001**: UI-based configuration via config flow (no YAML)
- **REQ-C002**: Zone creation with name and light selection
- **REQ-C003**: Per-zone configuration options:
  - Default transition time
  - Brightness range for adaptive
  - Color temp range for adaptive
  - Enable/disable specific layer types

#### 5.2 Device Registry
- **REQ-C004**: Each zone appears as a device in device registry
- **REQ-C005**: All zone entities grouped under zone device
- **REQ-C006**: Device info includes version and capabilities

### 6. Integrations

#### 6.1 Adaptive Lighting Integration
- **REQ-I001**: Read adaptive values from external sensors
- **REQ-I002**: Support sun-based calculations
- **REQ-I003**: Support time-based profiles
- **REQ-I004**: Support manual adaptive factor override

#### 6.2 Area Integration
- **REQ-I005**: Optionally link zones to Home Assistant areas
- **REQ-I006**: Auto-discover lights in area
- **REQ-I007**: Support area-wide presets

#### 6.3 Scene Integration
- **REQ-I008**: Layers can be activated by scenes
- **REQ-I009**: Layers can restore scene states
- **REQ-I010**: Support scene transition times

### 7. Performance Requirements

#### 7.1 Responsiveness
- **REQ-P001**: Layer state changes must trigger calculation within 100ms
- **REQ-P002**: Calculations must complete within 50ms for 10 layers
- **REQ-P003**: Light commands must be sent within 200ms of trigger

#### 7.2 Scalability
- **REQ-P004**: Support up to 20 zones per instance
- **REQ-P005**: Support up to 20 layers per zone
- **REQ-P006**: Support up to 50 lights per zone

#### 7.3 Efficiency
- **REQ-P007**: Use callback decorators for synchronous operations
- **REQ-P008**: Batch light commands when possible
- **REQ-P009**: Cache calculation results for identical inputs

### 8. User Experience Requirements

#### 8.1 Discoverability
- **REQ-U001**: All layers visible in entity list
- **REQ-U002**: All sensors visible with clear naming
- **REQ-U003**: Services documented with descriptions and examples

#### 8.2 Debuggability
- **REQ-U004**: Every state change must be observable in UI
- **REQ-U005**: Calculation path must be traceable
- **REQ-U006**: Conflicts must be clearly reported

#### 8.3 Predictability
- **REQ-U007**: Same inputs always produce same outputs
- **REQ-U008**: Priority rules must be consistent
- **REQ-U009**: No hidden state or side effects

### 9. Migration Requirements

#### 9.1 From YAML Configuration
- **REQ-M001**: Auto-import existing YAML config on first run
- **REQ-M002**: Convert input_numbers to layer entities
- **REQ-M003**: Preserve all settings and state

#### 9.2 Cleanup
- **REQ-M004**: Remove obsolete entities after migration
- **REQ-M005**: Archive old configuration
- **REQ-M006**: Provide rollback instructions

### 10. Testing Requirements

#### 10.1 Unit Tests
- **REQ-T001**: 100% coverage for calculator functions
- **REQ-T002**: Test all priority edge cases
- **REQ-T003**: Test conflict detection scenarios

#### 10.2 Integration Tests
- **REQ-T004**: Test full Calculate → Store → Apply flow
- **REQ-T005**: Test service calls
- **REQ-T006**: Test event firing

#### 10.3 Performance Tests
- **REQ-T007**: Benchmark calculation performance
- **REQ-T008**: Test with maximum supported entities
- **REQ-T009**: Memory usage profiling

## Implementation Priority

### Phase 1: Core Foundation (Must Have)
1. Layer entity platform (REQ-L001 through REQ-L008)
2. Basic orchestration engine (REQ-O001 through REQ-O004)
3. State calculation (REQ-O005 through REQ-O009)
4. State application (REQ-O014 through REQ-O017)
5. Basic services (REQ-A001 through REQ-A003)

### Phase 2: Observability (Must Have)
1. Calculation sensors (REQ-S001 through REQ-S004)
2. Core events (REQ-S008 through REQ-S012)
3. Config flow (REQ-C001 through REQ-C003)

### Phase 3: Advanced Features (Should Have)
1. Advanced services (REQ-A004 through REQ-A011)
2. Debug sensors (REQ-S005 through REQ-S007)
3. Conflict detection (REQ-O010 through REQ-O013)
4. Device registry (REQ-C004 through REQ-C006)

### Phase 4: Integrations (Nice to Have)
1. Adaptive lighting integration (REQ-I001 through REQ-I004)
2. Area integration (REQ-I005 through REQ-I007)
3. Scene integration (REQ-I008 through REQ-I010)

### Phase 5: Polish (Nice to Have)
1. Performance optimizations (REQ-P007 through REQ-P009)
2. Migration tools (REQ-M001 through REQ-M006)
3. Comprehensive testing (REQ-T001 through REQ-T009)

## Success Criteria

The implementation is considered successful when:

1. **Architectural Purity**: All state is observable in the UI, no hidden variables
2. **Predictability**: Given the same active layers, the same lights always result
3. **Debuggability**: Any lighting behavior can be traced to specific layer states
4. **Performance**: State changes apply to lights within 200ms
5. **Reliability**: No race conditions or conflicting automations
6. **Maintainability**: New features can be added without breaking existing behavior

## Appendix A: State Calculation Examples

### Example 1: Simple Priority
```python
Active Layers:
- base_adaptive (priority=0): brightness=100, color_temp=300
- environmental (priority=10): brightness=150, color_temp=250
- mode (priority=30): brightness=50, color_temp=400

Result: mode wins
Final State: brightness=50, color_temp=400, source="mode"
```

### Example 2: Force Override
```python
Active Layers:
- base_adaptive (priority=0, force=True): brightness=100, color_temp=300
- mode (priority=30): brightness=50, color_temp=400

Result: base_adaptive wins due to force flag
Final State: brightness=100, color_temp=300, source="base_adaptive"
```

### Example 3: Locked Layer
```python
Active Layers:
- manual (priority=100, locked=True): brightness=200, color_temp=350
Attempts to activate mode layer: REJECTED

Result: manual remains active and unchanged
Final State: brightness=200, color_temp=350, source="manual"
```

## Appendix B: Event Payloads

### layer_activated Event
```json
{
  "entity_id": "layer.living_room_mode",
  "zone_id": "living_room",
  "layer_id": "mode",
  "priority": 30,
  "state": {
    "brightness": 50,
    "color_temp": 400,
    "source": "automation.movie_time"
  }
}
```

### calculation_complete Event
```json
{
  "zone_id": "living_room",
  "timestamp": "2024-01-01T12:00:00Z",
  "active_layers": ["base_adaptive", "environmental", "mode"],
  "winning_layer": "mode",
  "final_state": {
    "brightness": 50,
    "color_temp": 400,
    "transition": 1.0
  },
  "calculation_time_ms": 12,
  "conflicts": []
}
```

## Appendix C: Service Call Examples

### Activate Movie Mode
```yaml
service: lighting_manager.activate_layer
target:
  entity_id: layer.living_room_mode
data:
  brightness: 30
  color_temp: 500
  transition: 5.0
  source: "automation.movie_night"
```

### Force Manual Override
```yaml
service: lighting_manager.force_layer
target:
  entity_id: layer.living_room_manual
data:
  brightness: 255
  locked: true
```

### Reset Zone to Baseline
```yaml
service: lighting_manager.reset_zone
data:
  zone_id: "living_room"
```
