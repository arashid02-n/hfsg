"""Shared Model B constants (MODEL.md sections 2, 4, 8).

Single source of truth for unit names, stock field names and flow
definitions. The transfer tuple order encodes the approved ICU allocation
priority: ED -> ICU, then Specialty -> ICU, then General Ward -> ICU.
"""

from __future__ import annotations

ACTIVE_UNITS = ("ed", "specialty", "general", "icu")

UNIT_TO_STOCK_FIELD = {
    "ed": "ed_census",
    "specialty": "specialty_census",
    "general": "general_census",
    "icu": "icu_census",
}

# (flow_name, source_unit, destination_unit) in approved processing order.
TRANSFERS = (
    ("T_EC", "ed", "specialty"),
    ("T_EG", "ed", "general"),
    ("T_EI", "ed", "icu"),
    ("T_CG", "specialty", "general"),
    ("T_CI", "specialty", "icu"),
    ("T_GI", "general", "icu"),
)

TRANSFER_NAMES = tuple(name for name, _, _ in TRANSFERS)

EXIT_FLOWS = {
    "T_EH": "ed",
    "D_C": "specialty",
    "D_G": "general",
    "D_I": "icu",
    "M_C": "specialty",
    "M_G": "general",
    "M_I": "icu",
}

DISCHARGE_FLOWS = {"D_C": "specialty", "D_G": "general", "D_I": "icu"}
DEATH_FLOWS = {"M_C": "specialty", "M_G": "general", "M_I": "icu"}

MOVEMENT_FLOW_NAMES = TRANSFER_NAMES + ("T_EH",)
FLOW_NAMES = MOVEMENT_FLOW_NAMES + tuple(DISCHARGE_FLOWS) + tuple(DEATH_FLOWS)
