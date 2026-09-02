"""Patient entity model and Patient Generator (MODEL.md sections 13, 19, 20).

This module is an HFSG engineering extension (not part of the source
paper). It creates patient entities for the initial population and for
admitted arrivals.

Every admitted arrival produces exactly one patient entity. Only
``admitted_arrivals`` enter the system (MODEL.md section 11 / approved ED
arrival rule); ``unmet_arrival_demand`` does NOT create patients.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

# Discrete severity ordering used by ICU-transfer priority and death
# weighting (higher value = more severe).
SEVERITY_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}

# Patient attribute fields sampled from configured distributions
# (MODEL.md section 20).
_ATTRIBUTE_FIELDS = ("age_group", "sex", "severity_level", "arrival_mode")


@dataclass
class Patient:
    """One patient entity."""

    simulation_id: str
    scenario_id: str
    patient_id: int
    arrival_datetime: str
    age_group: str
    sex: str
    severity_level: str
    arrival_mode: str
    initial_unit: str
    entry_type: str

    # Live simulation state (not part of the static output fields).
    current_unit: str = ""
    arrival_hour: Optional[int] = None
    model_arrival_hour: Optional[int] = None
    activity_start_hour: Optional[int] = None
    terminal_event: Optional[str] = None
    terminal_hour: Optional[int] = None

    def active_at(self, hour: int) -> bool:
        return (
            self.arrival_hour is not None
            and hour >= self.arrival_hour
            and self.terminal_event is None
        )

    @property
    def severity_rank(self) -> int:
        return SEVERITY_ORDER.get(self.severity_level, 0)


class PatientGenerator:
    """Creates patient entities using approved ASSUMPTION distributions."""

    def __init__(self, config, simulation_id: str, scenario_id: str, rng=None) -> None:
        self._config = config
        self._simulation_id = simulation_id
        self._scenario_id = scenario_id
        self._rng = rng if rng is not None else np.random.default_rng()
        self._next_id = 1

        attrs = config.patient_attributes
        self._attr_specs = {
            key: self._build_sampler(attrs[key]) for key in _ATTRIBUTE_FIELDS
        }

    # ------------------------------------------------------------------
    # Configuration readers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sampler(spec: Dict[str, Any]):
        categories = list(spec["categories"])
        probabilities = [float(p) for p in spec["probabilities"]]
        return categories, probabilities

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_rng(self, rng) -> None:
        self._rng = rng

    def _sample_attribute(self, rng, key: str) -> str:
        categories, probabilities = self._attr_specs[key]
        return str(rng.choice(categories, p=probabilities))

    def _new_patient(
        self,
        *,
        initial_unit: str,
        entry_type: str,
        arrival_datetime: str,
        arrival_hour: Optional[int],
        model_arrival_hour: Optional[int],
        rng,
    ) -> Patient:
        patient = Patient(
            simulation_id=self._simulation_id,
            scenario_id=self._scenario_id,
            patient_id=self._next_id,
            arrival_datetime=arrival_datetime,
            age_group=self._sample_attribute(rng, "age_group"),
            sex=self._sample_attribute(rng, "sex"),
            severity_level=self._sample_attribute(rng, "severity_level"),
            arrival_mode=self._sample_attribute(rng, "arrival_mode"),
            initial_unit=initial_unit,
            entry_type=entry_type,
        )
        self._next_id += 1
        patient.current_unit = initial_unit
        patient.arrival_hour = arrival_hour
        patient.model_arrival_hour = model_arrival_hour
        patient.activity_start_hour = arrival_hour
        return patient

    def create_initial_population(
        self, initial_stocks: Dict[str, int], start_datetime: str
    ) -> List[Patient]:
        """Create the initial patient population (MODEL.md section 13).

        ``initial_stocks`` maps active unit -> configured integer census.
        No prior-stay distribution is used; initial patients are present
        from hour 0 with ``entry_type=INITIAL``.
        """
        patients: List[Patient] = []
        for unit, count in initial_stocks.items():
            for _ in range(int(count)):
                patients.append(
                    self._new_patient(
                        initial_unit=unit,
                        entry_type="INITIAL",
                        arrival_datetime=start_datetime,
                        arrival_hour=0,
                        model_arrival_hour=0,
                        rng=self._rng,
                    )
                )
        return patients

    def create_arrival_patients(
        self,
        count: int,
        hour: int,
        arrival_datetime: str,
    ) -> List[Patient]:
        """Create patient entities for ``count`` admitted arrivals.

        Each admitted arrival is assigned the ED as initial unit
        (MODEL.md section 19). ``count`` is the approved integer number of
        admitted arrivals for the timestep, which the Patient Generator
        MUST NOT change.
        """
        if count < 0:
            raise ValueError(f"arrival patient count cannot be negative: {count}")
        patients: List[Patient] = []
        for _ in range(int(count)):
            patients.append(
                self._new_patient(
                    initial_unit="ed",
                    entry_type="ARRIVAL",
                    arrival_datetime=arrival_datetime,
                    arrival_hour=hour,
                    model_arrival_hour=hour,
                    rng=self._rng,
                )
            )
        return patients
