# Home Assistant Layer Manager

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A powerful Home Assistant integration that allows you to apply and manage multiple "layers" of states to your entities. This is incredibly useful for handling multiple notifications, alerts, and temporary states without losing the original states.

For example: Imagine your porch lights are on a dim, warm white for the evening. If your security camera detects motion, you can use Layer Manager to apply a high-priority "bright white" layer. When the motion clears, you simply remove that layer, and the lights automatically revert to their previous dim, warm state.

## Key Features

- **Layered State Management**: Apply scenes or states in layers with different priorities. The highest priority layer is always the one that is active.
- **UI-Based Configuration**: No YAML required for setup. Configure everything from the Home Assistant frontend.
- **State Persistence**: Layers are saved and restored across Home Assistant restarts.
- **Adaptive Lighting**: Automatically adjust the color temperature and brightness of your lights based on the sun's position or other sensor values.
- **Advanced Per-Entity Settings**: Override global adaptive lighting settings for individual lights that have special requirements.
- **Status Sensor**: A detailed sensor (`sensor.layer_manager_status`) exposes the integration's state for monitoring and advanced automations.

## Installation (HACS)

1. Ensure you have [HACS (Home Assistant Community Store)](https://hacs.xyz/) installed.
2. In the HACS interface, go to **Integrations**.
3. Click the three dots in the top right and select **"Custom repositories"**.
4. In the "Repository" field, paste the URL of this GitHub repository.
5. For "Category," select **"Integration"**.
6. Click **"Add"**.
7. Find the "Layer Manager" card and click **"Install"**.
8. **Restart Home Assistant** after the installation is complete.

## Configuration

Configuration is handled entirely through the Home Assistant UI.

1. Go to **Settings** -> **Devices & Services**.
2. Click the **+ ADD INTEGRATION** button in the bottom right.
3. Search for **"Layer Manager"** and click on it.
4. The integration will be added. Now, click the **cog** on the newly added card to set it up.

You will be presented with a menu:

- **Manage Managed Lights**: Select all the supported entities you want this integration to control. This is the most important step.
- **Global Settings**: Configure the default parameters for Adaptive Lighting that will apply to all managed lights.
- **Configure advanced settings for a specific light**: Fine-tune the adaptive lighting behavior for individual lights, overriding the global settings.

## Features

### Sensors

The integration creates two sensors:

- **`sensor.layer_manager_status`**: The state of this sensor is the number of layers active. The real value is in its **attributes**, which contain a complete, real-time snapshot of all entity layers and adaptive tracks. This is perfect for diagnostics and complex automations.

### Services

These are the core tools you will use in your automations to control the light layers.

| Service | Description |
| :--- | :--- |
| `layer_manager.insert_scene` | Applies a pre-defined Home Assistant scene as a layer to all managed lights within that scene. |
| `layer_manager.insert_state` | Applies a custom state (e.g., on/off, color, brightness) as a layer to a specific light or group. |
| `layer_manager.remove_layer` | Removes a layer by its ID, causing the light to revert to the next highest priority layer (or turn off if no layers remain). |
| `layer_manager.add_adaptive` | Temporarily enables adaptive brightness and/or color temperature for a light or group. |
| `layer_manager.remove_adaptive`| Removes a light or group from adaptive tracking. |
| `layer_manager.refresh` | Forces a specific light or group to re-evaluate its current state. |
| `layer_manager.refresh_all` | Refreshes all managed lights. |

#### Service Call Examples

**Applying a "Security Alert" Layer**

This applies a high-priority (priority 100) layer that makes a light flash red.

```yaml
service: layer_manager.insert_state
data:
  entity_id: light.patio_light
  id: "security_alert_patio" # A unique name for this layer
  priority: 100
  state: "on"
  attributes:
    rgb_color:
    effect: "flash"
```

#### Removing the "Security Alert" layer

When the alert is over, remove the layer by its unique ID. The light will revert to its previous state automatically.

```yaml
service: layer_manager.remove_layer
data:
  id: "security_alert_patio"
```

### Example Automation

This automation flashes the porch light when motion is detected and restores its previous state after one minute.

```yaml
automation:
  - alias: "Porch Motion Light Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.porch_motion
        to: "on"
    action:
      - service: layer_manager.insert_state
        data:
          entity_id: light.porch_main
          id: "motion_alert"
          priority: 50
          attributes:
            brightness: 255
            effect: "fast_blink"
      - delay: "00:01:00"
      - service: layer_manager.remove_layer
        data:
          id: "motion_alert"
```
