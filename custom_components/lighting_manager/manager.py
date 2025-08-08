"""Core calculation logic for Lighting Manager."""
from __future__ import annotations

from typing import Any, List

from homeassistant.core import HomeAssistant

from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_FORCE,
    ATTR_LOCKED,
    ATTR_PRIORITY,
    ATTR_RGB_COLOR,
    ATTR_SOURCE,
    ATTR_TRANSITION,
    DEFAULT_LAYERS,
)


class LightingManager:
    """Calculate final light states based on layer entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        zone_id: str,
        lights: List[str],
        adaptive: dict | None = None,
    ) -> None:
        self.hass = hass
        self.zone_id = zone_id
        self.lights = lights
        self.adaptive = adaptive or {}
        self.layer_entity_ids = [
            f"layer.{zone_id}_{layer_id}" for layer_id in DEFAULT_LAYERS
        ]

    def active_layers(self) -> List[str]:
        """Return active layer entity IDs."""
        active: List[str] = []
        for ent_id in self.layer_entity_ids:
            state = self.hass.states.get(ent_id)
            if state and str(state.state).lower() in ("on", "true", "1"):
                active.append(ent_id)
        return active

    def calculate_zone_state(self) -> dict[str, Any]:
        """Compute the final state for the zone lights."""
        active_layers = []
        for ent_id in self.layer_entity_ids:
            state = self.hass.states.get(ent_id)
            if not state or str(state.state).lower() not in (
                "on",
                "true",
                "1",
            ):
                continue
            attrs = state.attributes
            active_layers.append(
                {
                    "entity_id": ent_id,
                    "layer_id": ent_id.split(".")[1].split("_")[1],
                    ATTR_PRIORITY: attrs.get(ATTR_PRIORITY, 0),
                    ATTR_FORCE: attrs.get(ATTR_FORCE, False),
                    ATTR_LOCKED: attrs.get(ATTR_LOCKED, False),
                    ATTR_BRIGHTNESS: attrs.get(ATTR_BRIGHTNESS),
                    ATTR_COLOR_TEMP: attrs.get(ATTR_COLOR_TEMP),
                    ATTR_RGB_COLOR: attrs.get(ATTR_RGB_COLOR),
                    ATTR_TRANSITION: attrs.get(ATTR_TRANSITION),
                    ATTR_SOURCE: attrs.get(ATTR_SOURCE),
                }
            )

        forced_layers = [layer for layer in active_layers if layer[ATTR_FORCE]]
        candidates = forced_layers if forced_layers else active_layers
        if not candidates:
            return {
                "active_layers": [],
                "winning_layer": None,
                "final_state": {},
            }

        winner = max(candidates, key=lambda layer: layer[ATTR_PRIORITY])
        final_state: dict[str, Any] = {}
        for key in (
            ATTR_BRIGHTNESS,
            ATTR_COLOR_TEMP,
            ATTR_RGB_COLOR,
            ATTR_TRANSITION,
        ):
            if winner.get(key) is not None:
                final_state[key] = winner[key]
        final_state[ATTR_SOURCE] = winner.get(ATTR_SOURCE)
        return {
            "active_layers": [layer["layer_id"] for layer in active_layers],
            "winning_layer": winner["layer_id"],
            "final_state": final_state,
        }
