from homeassistant.components.light import DOMAIN as DOMAIN_LIGHT
from homeassistant.components.switch import DOMAIN as DOMAIN_SWITCH
from homeassistant.components.number import DOMAIN as DOMAIN_NUMBER
from homeassistant.components.select import DOMAIN as DOMAIN_SELECT
from homeassistant.components.input_boolean import DOMAIN as DOMAIN_INPUT_BOOLEAN
from homeassistant.components.input_number import DOMAIN as DOMAIN_INPUT_NUMBER
from homeassistant.components.input_select import DOMAIN as DOMAIN_INPUT_SELECT
from homeassistant.components.cover import DOMAIN as DOMAIN_COVER

DOMAIN = "layer_manager"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}-states"

# DATA_ENTITIES = "lm-entities"
# DATA_STATES = "lm-states"
# DATA_ADAPTIVE_ENTITIES = "lm-adaptive-entities"
# DATA_COORDINATOR = "coordinator"

SERVICE_INSERT_SCENE = "insert_scene"
SERVICE_INSERT_STATE = "insert_state"
SERVICE_REMOVE_LAYER = "remove_layer"
SERVICE_REMOVE_ALL_LAYERS = "remove_all_layers"
SERVICE_REFRESH_ALL = "refresh_all"
SERVICE_REFRESH = "refresh"
SERVICE_ADD_ADAPTIVE = "add_adaptive"
SERVICE_REMOVE_ADAPTIVE = "remove_adaptive"

ATTR_PRIORITY = "priority"
ATTR_ATTRIBUTES = "attributes"
ATTR_CLEAR_LAYER = "clear_layer"
ATTR_COLOR = "color"
ATTR_COLOR_TEMP = "color_temp"

CONF_ENTITIES = "entities"
CONF_ADAPTIVE = "adaptive"
CONF_MAX_COLOR_TEMP = "color_temp_max"
CONF_MIN_COLOR_TEMP = "color_temp_min"
CONF_MAX_BRIGHTNESS = "brightness_max"
CONF_MIN_BRIGHTNESS = "brightness_min"
CONF_MAX_ELEVATION = "elevation_max"
CONF_MIN_ELEVATION = "elevation_min"
CONF_ADAPTIVE_INPUT_ENTITIES = "adaptive_input_entities"
CONF_INPUT_BRIGHTNESS_MAX = "input_brightness_max"
CONF_INPUT_BRIGHTNESS_MIN = "input_brightness_min"
CONF_INPUT_BRIGHTNESS_ENTITY = "input_brightness_entity"
CONF_DEFAULT_STATE = "default_state"

SUPPORTED_DOMAINS = [
    DOMAIN_LIGHT, DOMAIN_COVER, DOMAIN_NUMBER, DOMAIN_SELECT, DOMAIN_INPUT_BOOLEAN, DOMAIN_INPUT_NUMBER, DOMAIN_SWITCH, DOMAIN_INPUT_SELECT
]

DEFAULT_CONF_NAME = "Layer Manager"

SIGNAL_DATA_UPDATE = f"{DOMAIN}-data-changed"
