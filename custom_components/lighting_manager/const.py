"""Constants for Lighting Manager integration."""

DOMAIN = "lighting_manager"

# Config keys
CONF_ENTITIES = "entities"
CONF_ZONE = "zone_id"
CONF_MIN_ELEVATION = "elevation_min"
CONF_MAX_ELEVATION = "elevation_max"

# Layer defaults
LAYER_BASE_ADAPTIVE = "base_adaptive"
LAYER_ENVIRONMENTAL = "environmental"
LAYER_ACTIVITY = "activity"
LAYER_MODE = "mode"
LAYER_MANUAL = "manual"

DEFAULT_LAYERS = {
    LAYER_BASE_ADAPTIVE: 0,
    LAYER_ENVIRONMENTAL: 10,
    LAYER_ACTIVITY: 20,
    LAYER_MODE: 30,
    LAYER_MANUAL: 100,
}

# Layer state attributes
ATTR_ACTIVE = "active"
ATTR_BRIGHTNESS = "brightness"
ATTR_COLOR_TEMP = "color_temp"
ATTR_RGB_COLOR = "rgb_color"
ATTR_TRANSITION = "transition"
ATTR_FORCE = "force"
ATTR_LOCKED = "locked"
ATTR_CONDITIONS = "conditions"
ATTR_LAST_UPDATED = "last_updated"
ATTR_SOURCE = "source"
ATTR_PRIORITY = "priority"

# Services
SERVICE_ACTIVATE_LAYER = "activate_layer"
SERVICE_DEACTIVATE_LAYER = "deactivate_layer"
SERVICE_UPDATE_LAYER = "update_layer"
SERVICE_SET_LAYER_PRIORITY = "set_layer_priority"
SERVICE_RECALCULATE_ZONE = "recalculate_zone"
SERVICE_RESET_ZONE = "reset_zone"

SIGNAL_LAYER_UPDATE = f"{DOMAIN}-update"

# Platforms
PLATFORMS = ["layer", "sensor"]
