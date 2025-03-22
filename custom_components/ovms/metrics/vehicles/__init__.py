"""Vehicle-specific metrics for OVMS integration."""

from .vw_eup import VW_EUP_METRICS
from .smart_fortwo import SMART_FORTWO_METRICS
from .mg_zs_ev import MG_ZS_EV_METRICS
from .nissan_leaf import NISSAN_LEAF_METRICS

# Add imports for future vehicle-specific metric sets here
# from .tesla_model_s import TESLA_MODEL_S_METRICS
# from .renault_zoe import RENAULT_ZOE_METRICS

# Export all vehicle metrics for use in the main metrics module
__all__ = [
    "VW_EUP_METRICS",
    "SMART_FORTWO_METRICS",
    "MG_ZS_EV_METRICS",
    "NISSAN_LEAF_METRICS",
    # "TESLA_MODEL_S_METRICS",
    # "RENAULT_ZOE_METRICS",
]
