# Home Assistant Lighting Manager

Allows layers to be applied to lights. Useful for multiple levels of notifications and restoring states.

For example: If I want outdoor lights that are a dim white at night, I would add a scene at layer 0 (the lowest.) If something at night happens such as a home security system being triggered while I'm away, an automation would insert an alarm scene at a higher layer and be visible over the night time scene. Now if somehow the sun rises while the alarm scene is scening, to prevent an automation from turning the lights off, one would  remove the night time scene from the bulbs' layers resulting in the alarm scene to still be active. When that scene is removed, the lights would look for the next lowest layer and turn off due to absence of a layer. Layers can endlessly be stacked and mixed to render smarter lighting scenes.

## Configuration
Example configuration.yaml entry:
```
lighting_manager:
  entities:
    - light.porch_light_1
    - light.porch_light_2
    - light.foh_light_1
    - light.foh_light_2
    - light.foh_light_3
```
## Services

### lighting_manager.insert_scene
Apply a scene at a specified layer. All lights managed by lighting manager and in the specified scene will be updated with priority states. Any unmanaged lights and other entities will be updated as if scene.apply was called.

#### Service Parameters
| Parameter | Description |
|-----------|-------------|
| entity_id | Entity ID of scene to be inserted. |
| priority | Layer priority. Higher values will appear before lower. |

### lighting_manager.remove_scene
Remove a scene from layers. All lights affected will be updated. This will not restore changes to unmanaged lights and other entities that are in the specified scene.

#### Service Parameters
| Parameter | Description |
|-----------|-------------|
| entity_id | Entity ID of scene to be removed. |
### lighting_manager.insert_state
Apply lighting attributes to a light entity at the specified priority. If light was not specified in the configuration, nothing will happen.

#### Service Parameters
| Parameter | Description |
|-----------|-------------|
| entity_id | Entity ID of light. |
| priority | Layer priority. Higher values will appear before lower. |
| id | Layer ID. Used when removing the state from layers.
| attributes | A dictionary of light state attributes to be applied.

### lighting_manager.remove_state
Remove a state layer by id from the specified entity.

#### Service Parameters
| Parameter | Description |
|-----------|-------------|
| entity_id | Entity ID of light. |
| id | Layer ID to be removed.
