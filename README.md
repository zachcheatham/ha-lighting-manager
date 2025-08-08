# Lighting Manager Home Assistant Custom Component

**Version:** 0.0.5
**Domain:** `lighting_manager`

This custom component exposes a set of services and a helper sensor that make it easy to layer multiple lighting scenes, apply arbitrary states to lights and other entities, and implement automatic brightness and color‑temperature adaptation. It allows you to stack different lighting “layers” with priorities (for example, base ambience, a holiday scene and a warning indicator), refresh the state of individual lights or all managed entities, and automatically adjust lights based on the position of the sun and optional brightness sensors.

The component is entirely implemented using Home Assistant’s entity, state and service APIs. All state changes are reproduced via Home Assistant’s built‑in `async_reproduce_state` call and therefore respect current integrations and transitions. Lights are automatically removed from adaptive tracking when they are turned off, and they will restore their layered state when they become available again.

## Features

### Layer Entities

* **Layer concept:** Each configured zone automatically creates five predefined `layer` entities (`base_adaptive`, `environmental`, `activity`, `mode`, and `manual`). Each layer holds optional brightness and colour settings along with a priority value. The active layer with the highest priority controls the lights in the zone.
* **Layer activation:** Call the `lighting_manager.activate_layer` service targeting a `layer` entity to activate it. You may supply `brightness`, `color_temp`, `rgb_color`, `transition`, `force`, or `locked` flags as needed.
* **Layer update/deactivation:** Use `lighting_manager.update_layer` to modify a layer's attributes without changing its activation state. Use `lighting_manager.deactivate_layer` to turn a layer off.

### Adaptive Brightness and Color Temperature

The component can automatically adjust a light’s brightness and colour temperature based on the sun’s elevation and/or one or more input sensors. Two mechanisms are provided:

1. **Inline adaptive attributes** – You can embed the string `"adaptive"` into the `brightness` or `color_temp` attributes of a state to instruct the component to compute those values automatically. Optional key–value pairs may follow the adaptive keyword separated by semicolons (`;`). Recognised keys for brightness are:

   * `brightness_max`: maximum brightness (0–255)
   * `brightness_min`: minimum brightness (0–255)
   * `input_brightness_min`: minimum value read from the input sensor
   * `input_brightness_max`: maximum value read from the input sensor
   * `input_brightness_entity`: entity ID of the sensor providing a brightness input

   For colour temperature you can provide `min_color_temp` and `max_color_temp`. If you omit any of these keys they fall back to per‑entity adaptive defaults (defined under the entity’s configuration) or global adaptive defaults (defined under the component’s `adaptive` section). When a state containing an adaptive attribute is applied, the component registers the entity in the adaptive tracking list (`DATA_ADAPTIVE_ENTITIES`). The attributes are recomputed whenever the sun’s position or any configured brightness input changes.

2. **Services** – You can call the `add_adaptive` service to start adaptive behaviour on a light or group of lights without replacing existing layered states. The `brightness` and `color_temp` options determine whether brightness and colour temperature should be adapted. Passing `true` enables adaptation; passing an integer for `brightness` immediately turns the light on at that brightness but still registers it for ongoing adaptation. Use the `remove_adaptive` service to stop adaptation and remove the light from the tracking list. Lights automatically remove themselves when turned off.

### Adaptive Lighting Factor Sensor

The component exposes a sensor named **`sensor.adaptive_lighting_factor`**. It calculates a floating‑point factor between 0 and 1 based on the current sun elevation. By default the factor is 1.0 at sunrise/sunset and decays to 0.0 when the sun is at its maximum height. The formula clamps the sun’s elevation between `min_elevation` and `max_elevation` (configured globally) and computes:

```
adaptive_factor = 1.0 - (elevation_clamped / max_elevation)
```

This factor drives the adaptive colour temperature algorithm. Lower factors yield cooler temperatures, while higher factors yield warmer temperatures. You can read this sensor for informational purposes or incorporate it into automations. The code for the sensor resides in `sensor.py`, and it reacts to changes in the `sun.sun` entity.

## Requirements

* Home Assistant 2022.10 or later.
* The component must be placed in your Home Assistant configuration directory under `custom_components/lighting_manager/` with the files `__init__.py`, `sensor.py`, `services.yaml` and `manifest.json`.
* A working `sun` integration for adaptive colour temperature. For brightness adaptation you need one or more numeric sensors whose entity IDs you specify in the configuration.
* Only lights (domain `light`) can adapt brightness or colour temperature. Other domains can still participate in layered scenes and states but will ignore adaptive attributes.

## Installation

1. Copy the `lighting_manager` folder into your Home Assistant `custom_components` directory:

   ```
   <config>/custom_components/
   └── lighting_manager/
       ├── __init__.py
       ├── sensor.py
       ├── manifest.json
       └── services.yaml
   ```

2. Restart Home Assistant.

3. After restart, the component registers its services under the `lighting_manager` domain and creates the `sensor.adaptive_lighting_factor` sensor.

## Configuration

Add the following section to your `configuration.yaml`. Only the `entities` key is required; all other options are optional. The schema below is summarised from the component code.

```yaml
lighting_manager:
  entities:
    <entity_id>:
      adaptive:
        color_temp_min: <int or null>     # Minimum mired value for adaptive colour temperature
        color_temp_max: <int or null>     # Maximum mired value for adaptive colour temperature
        brightness_min: <int>             # Minimum brightness (0–255) when adapting
        brightness_max: <int>             # Maximum brightness (0–255) when adapting
        input_brightness_entity: <str>    # (Optional) Sensor entity supplying brightness input
        input_brightness_min: <int or null> # Minimum value read from the input sensor
        input_brightness_max: <int or null> # Maximum value read from the input sensor
    # repeat for each managed light

  adaptive:
    min_elevation: <int>           # Default 0; lower clamp for sun elevation
    max_elevation: <int>           # Default 15; upper clamp for sun elevation
    min_color_temp: <int>          # Default 153; global fallback for colour temperature
    max_color_temp: <int>          # Default 333; global fallback for colour temperature
    input_brightness_entity: <str> # (Optional) global brightness input sensor
    adaptive_input_entities:
      - <entity_id>                # List of sensors that trigger brightness updates on change
    input_brightness_min: <int>    # Default 0; global minimum value of brightness sensor
    input_brightness_max: <int>    # Default 255; global maximum value of brightness sensor
```

### Explanation of configuration keys

* **`entities`** – A dictionary mapping entity IDs (lights, or groups of lights) to configuration. Only entities listed here are managed. Groups will be automatically ungrouped when acting on layers. If no per‑entity configuration is provided, defaults are used. Managed lights maintain a per‑entity record of layered states (`DATA_STATES`).
* **`adaptive`** – Global configuration for adaptive lighting. These values are used when a state contains the `adaptive` keyword or when you call `add_adaptive`. If you omit this section entirely, sensible defaults are used (min elevation 0, max elevation 15, colour temperature range 153–333 mireds, brightness range 0–255).
* **Per‑entity `adaptive`** – Overrides global adaptive values on a per‑light basis. Only values you specify here take effect; unspecified items fall back to global defaults.
* **`color_temp_min`/`color_temp_max`** – The mired range used when computing adaptive colour temperature. Warmer colour temperatures have higher mired values.
* **`brightness_min`/`brightness_max`** – The brightness range used when computing adaptive brightness (0 = off, 255 = full brightness). If not provided, defaults to 150/255 as set in the code.
* **`input_brightness_entity`** – Name of a numeric sensor whose reading is used to adjust the adaptive brightness. The reading is scaled between `input_brightness_min` and `input_brightness_max` to produce a factor. When omitted, the component uses the global `input_brightness_entity` or no sensor at all.
* **`input_brightness_min`/`input_brightness_max`** – Clamp values for the brightness input sensor. The reading is mapped to a range of 0–1 using these bounds. If omitted, the component defaults to 0 and 255 respectively.
* **`adaptive_input_entities`** – A list of entity IDs (usually sensors) that trigger brightness updates when they change. The entities listed here do not directly provide brightness values; instead they act as triggers to recalculate brightness for all lights being adaptively tracked.

After configuration, restart Home Assistant. You will see the `sensor.adaptive_lighting_factor` sensor and the `lighting_manager` services in Developer Tools → Services.

## Services

All services live under the domain `lighting_manager`. You can call them via automations, scripts or the Service Developer Tool.

### `lighting_manager.insert_scene`

Apply a Home Assistant scene to managed lights on a named layer.

| Field         | Required | Description                                                                                                                                                                             | Example                  |
| ------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| `entity_id`   | ✓        | The entity ID of a scene to apply. Groups within the scene are automatically expanded.                                                                                                  | `scene.evening_ambiance` |
| `id`          | ✓        | Unique identifier of the target layer. Each layer holds one scene or set of states.                                                                                                     | `movie_night`            |
| `priority`    | ✓        | Numeric priority of the layer. Higher numbers override lower ones.                                                                                                                      | `10`                     |
| `clear_layer` |          | If `true`, clears any existing states on the layer before applying.                                                                                                                     | `true`                   |
| `color`       |          | A three‑ or four‑element list `[R,G,B(,W)]` used to fill placeholder colour attributes in the scene (the code replaces attributes equal to the constant `ATTR_COLOR` with this colour). | `[255, 0, 0]`            |

When you call this service, the component extracts all entity states defined by the scene. If an entity is a group, its member entities are added individually. Managed lights store the resulting state in the specified layer along with its priority. Non‑managed entities are turned on/off immediately without being stored.

#### Example

```yaml
service: lighting_manager.insert_scene
data:
  entity_id: scene.holiday
  id: holiday_layer
  priority: 5
  clear_layer: true
  color: [0, 255, 0]
```

### `lighting_manager.insert_state`

Insert an arbitrary state for an entity or group into a named layer. This is useful for simple on/off actions, adjusting brightness or colour on the fly, or creating your own scenes without using the Scene editor.

| Field         | Required | Description                                                                                                                                                                                        | Example                                         |
| ------------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `entity_id`   | ✓        | Entity ID of the target light, switch, sensor or group. Groups are automatically expanded so that each light receives the state.                                                                   | `light.desk_lamp` or `group.living_room_lights` |
| `priority`    | ✓        | Numeric priority of the layer. Higher numbers override lower ones.                                                                                                                                 | `20`                                            |
| `id`          | ✓        | Unique identifier of the layer.                                                                                                                                                                    | `alert`                                         |
| `state`       |          | Desired state (e.g., `on`, `off`). Defaults to `on` if omitted.                                                                                                                                    | `on`                                            |
| `attributes`  |          | A dictionary of state attributes such as `brightness`, `color_temp`, `rgb_color`, `effect`, etc. Use the special value `"adaptive"` to enable adaptive behaviour (see the Adaptive section above). | `{"brightness": "adaptive;min=100;max=255"}`    |
| `clear_layer` |          | If `true`, clears other states from the layer before applying.                                                                                                                                     | `true`                                          |

#### Example

```yaml
service: lighting_manager.insert_state
data:
  entity_id: group.bedroom_lights
  id: bedtime
  priority: 15
  state: on
  attributes:
    brightness: adaptive;min=40;max=180
    color_temp: adaptive;min=230;max=400
  clear_layer: false
```

### `lighting_manager.remove_layer`

Remove a previously inserted layer from all managed lights or from a specified entity/group. Removing a layer reveals whatever lower‑priority layer remains for each light.

| Field       | Required | Description                                                                              | Example         |
| ----------- | -------- | ---------------------------------------------------------------------------------------- | --------------- |
| `entity_id` |          | Entity ID of a light or group. If omitted, the layer is removed from all managed lights. | `light.kitchen` |
| `id`        | ✓        | Layer ID to be removed.                                                                  | `holiday_layer` |

#### Example

```yaml
service: lighting_manager.remove_layer
data:
  id: holiday_layer
```

### `lighting_manager.refresh`

Immediately refresh the state of a single managed entity or group. This is useful when you suspect that states have drifted or when an entity becomes available after being unavailable. The component also calls this function automatically when a light changes from `unavailable` to `on` or `off`.

| Field       | Required | Description                                 | Example                    |
| ----------- | -------- | ------------------------------------------- | -------------------------- |
| `entity_id` | ✓        | Entity ID of the light or group to refresh. | `group.living_room_lights` |

### `lighting_manager.refresh_all`

Refresh all managed lights to their current rendered state. No parameters.

#### Example

```yaml
service: lighting_manager.refresh_all
```

### `lighting_manager.add_adaptive`

Begin adaptive brightness and colour‑temperature updates for a light or a group of lights. The light(s) remain in adaptive mode until turned off or removed with `remove_adaptive`. When a light is already in a layered state, adaptive values overlay on top of the current attributes.

| Field        | Required | Description                                                                                                                                                                               | Example         |
| ------------ | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| `entity_id`  | ✓        | Entity ID of a light or group containing lights.                                                                                                                                          | `light.bedroom` |
| `brightness` |          | Boolean or integer. `true` enables adaptive brightness; an integer turns the light on to that brightness immediately and then enables adaptation; `false` disables brightness adaptation. | `true`          |
| `color_temp` |          | Boolean. `true` enables adaptive colour‑temperature adjustments; `false` disables it.                                                                                                     | `true`          |

If neither `brightness` nor `color_temp` are specified, both default to `true`. After calling this service the light(s) will be tracked in `DATA_ADAPTIVE_ENTITIES`, and the component will recompute their attributes whenever the sun moves or input sensors change.

#### Example

```yaml
service: lighting_manager.add_adaptive
data:
  entity_id: light.desk_lamp
  brightness: 120
  color_temp: true
```

### `lighting_manager.remove_adaptive`

Stop adaptive updates for a light or group. The light retains its current attributes but will no longer change automatically.

| Field       | Required | Description                    | Example                |
| ----------- | -------- | ------------------------------ | ---------------------- |
| `entity_id` | ✓        | Entity ID of a light or group. | `group.bedroom_lights` |

#### Example

```yaml
service: lighting_manager.remove_adaptive
data:
  entity_id: group.bedroom_lights
```

## Adaptive Attribute Syntax

When inserting states, the `attributes` dictionary can contain strings that begin with the word `adaptive` to enable time‑of‑day and sensor based adjustments. The syntax is:

```
adaptive[;key=value][;key=value]…
```

Keys and meanings:

| Key                       | Applies to  | Description                                                           |
| ------------------------- | ----------- | --------------------------------------------------------------------- |
| `brightness_min`          | brightness  | Minimum brightness (0–255). Overrides per‑entity and global defaults. |
| `brightness_max`          | brightness  | Maximum brightness (0–255).                                           |
| `input_brightness_min`    | brightness  | Minimum reading of the input sensor.                                  |
| `input_brightness_max`    | brightness  | Maximum reading of the input sensor.                                  |
| `input_brightness_entity` | brightness  | Entity ID of the sensor providing brightness input.                   |
| `min_color_temp`          | colour temp | Minimum mired value for colour temperature.                           |
| `max_color_temp`          | colour temp | Maximum mired value for colour temperature.                           |

Unknown keys are ignored and logged as warnings.

### Example state with adaptive brightness and colour temperature

```yaml
service: lighting_manager.insert_state
data:
  entity_id: light.kitchen
  id: evening
  priority: 10
  state: on
  attributes:
    brightness: adaptive;brightness_min=80;brightness_max=200;input_brightness_entity=sensor.illuminance
    color_temp: adaptive;min_color_temp=200;max_color_temp=350
```

## Entity Restoration and Automatic Updates

Lights or groups may go through unavailable → available transitions (for example, when a bulb reconnects to the network). The component listens for such state changes and automatically re‑renders the layered state for that entity. It also listens for changes to the `sun.sun` entity and any configured brightness sensors to update adaptive values in real time.

Lights that are turned off are automatically removed from the adaptive tracking list. When turned back on they must be re‑added via `add_adaptive` or via an adaptive attribute in a new state.

## Notes and Caveats

* **Effect attribute:** When inserting states for lights without specifying the `effect` attribute, the component forces `effect: "None"` to ensure that lights are not left in a lingering effect mode.
* **Colour lists:** The `color` argument to `insert_scene` can be three or four elements. If the scene contains `rgbw_color` attributes they will be padded or truncated accordingly.
* **Groups:** Groups are only used as a convenience for targeting multiple lights. You cannot store a layered state on a group entity; rather each member light receives its own stored state.
* **Adaptive remove behaviour:** `remove_adaptive` only stops automatic updates; it does not revert the light to a previous layer. Use `remove_layer` or insert a new state to change the light.

## License and Acknowledgements

This component is authored by [@zachcheatham](https://github.com/zachcheatham) and is provided here for informational purposes only. The documentation above was derived from inspecting the source code (`__init__.py`, `sensor.py` and `services.yaml`) and the embedded schemas. For the latest updates please consult the official repository at the URL specified in `manifest.json`.

---

Above is the complete README content as requested.

