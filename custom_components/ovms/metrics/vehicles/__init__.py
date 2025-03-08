"""Vehicle-specific metrics for OVMS integration."""

from .vw_eup import VW_EUP_METRICS

# Add imports for future vehicle-specific metric sets here
# from .tesla_model_s import TESLA_MODEL_S_METRICS
# from .nissan_leaf import NISSAN_LEAF_METRICS
# from .renault_zoe import RENAULT_ZOE_METRICS

# Export all vehicle metrics for use in the main metrics module
__all__ = [
    "VW_EUP_METRICS",
    # "TESLA_MODEL_S_METRICS",
    # "NISSAN_LEAF_METRICS",
    # "RENAULT_ZOE_METRICS",
]
