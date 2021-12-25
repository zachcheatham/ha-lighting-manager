# Home Assistant Lighting Manager

Instead of maintaining one previous light state using scene.create, this integration allows lights to maintain layers that can be added to or removed from in any order. Very useful for lights that can indicate multiple alerts or other entity's state.

## Installation

1) Install this repository via HACS

2) Configure the integration via configuration.yaml

Example Configuration
```
lighting_manager:
  entities:
    - light.porch_light_1
    - light.porch_light_2
    - light.foh_light_1
    - light.foh_light_2
    - light.foh_light_3
```

Each light that should be "managed" must be listed in the entities array of the configuration.

## Additional Links

[README](https://github.com/zachcheatham/ha-lighting-manager/blob/master/README.md)

[Repository](https://github.com/zachcheatham/ha-lighting-manager)