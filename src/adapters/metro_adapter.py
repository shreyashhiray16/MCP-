"""
src/adapters/metro_adapter.py

Adapter for curated Pune Metro data.
Validates metro.json using Pydantic at startup.
Provides line information, station lookup, and fare calculation.
"""

import json
import logging
import sys
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError
from ..config import METRO_DATA_PATH

logger = logging.getLogger("pune_transit.metro")


class MetroLine(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    first_train: str
    last_train: str
    frequency_mins_peak: Optional[int] = None
    frequency_mins_offpeak: Optional[int] = None
    stations: List[str]


class MetroStation(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    lines: List[str]


class FareSlab(BaseModel):
    max_stations: int
    fare_inr: int


class FareRules(BaseModel):
    min_fare: int
    slabs: List[FareSlab]


class MetroDataSchema(BaseModel):
    last_verified: str
    source_url: str
    notes: Optional[str] = None
    lines: List[MetroLine]
    stations: List[MetroStation]
    fare_rules: FareRules


class MetroAdapter:
    def __init__(self, data_path: str = METRO_DATA_PATH):
        self.data_path = data_path
        self.is_available = False
        self.data: Optional[MetroDataSchema] = None
        self._stations_by_id: Dict[str, MetroStation] = {}
        self._lines_by_id: Dict[str, MetroLine] = {}
        self.load_data()

    def load_data(self):
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
            self.data = MetroDataSchema.model_validate(raw_json)
            self._stations_by_id = {s.id: s for s in self.data.stations}
            self._lines_by_id = {l.id: l for l in self.data.lines}
            self.is_available = True
            logger.info(f"Loaded Pune Metro data successfully (verified: {self.data.last_verified})")
        except FileNotFoundError:
            sys.stderr.write(f"[WARN] Metro data file not found at {self.data_path}. Metro features disabled.\n")
            self.is_available = False
        except ValidationError as ve:
            sys.stderr.write(f"[WARN] Metro data validation failed at {self.data_path}: {ve}. Metro features disabled.\n")
            self.is_available = False
        except Exception as e:
            sys.stderr.write(f"[WARN] Failed to load metro data: {e}\n")
            self.is_available = False

    def get_all_stations(self) -> List[Dict[str, Any]]:
        if not self.is_available or not self.data:
            return []
        return [s.model_dump() for s in self.data.stations]

    def find_station(self, name_or_id: str) -> Optional[MetroStation]:
        if not self.is_available or not self.data:
            return None
        norm = name_or_id.lower().strip()
        # Direct id check
        if norm in self._stations_by_id:
            return self._stations_by_id[norm]
        # Match by name
        for s in self.data.stations:
            if s.name.lower() == norm or norm in s.name.lower() or s.id == norm:
                return s
        return None

    def find_line(self, line_name_or_id: str) -> Optional[MetroLine]:
        if not self.is_available or not self.data:
            return None
        norm = line_name_or_id.lower().strip()
        if norm in self._lines_by_id:
            return self._lines_by_id[norm]
        for l in self.data.lines:
            if l.name.lower() == norm or norm in l.name.lower() or (l.color and l.color.lower() in norm):
                return l
        return None

    def calculate_fare(self, station1_id: str, station2_id: str) -> Optional[int]:
        """
        Calculates approximate fare between two stations based on network distance/station count.
        """
        if not self.is_available or not self.data:
            return None
        if station1_id == station2_id:
            return self.data.fare_rules.min_fare

        # Find shortest station hop count
        s1 = self._stations_by_id.get(station1_id)
        s2 = self._stations_by_id.get(station2_id)
        if not s1 or not s2:
            return None

        # Check if on same line
        common_lines = set(s1.lines).intersection(set(s2.lines))
        station_hop_count = 999
        if common_lines:
            line_id = next(iter(common_lines))
            line = self._lines_by_id[line_id]
            idx1 = line.stations.index(station1_id)
            idx2 = line.stations.index(station2_id)
            station_hop_count = abs(idx1 - idx2)
        else:
            # Different lines -> transfer at civil_court
            interchange = "civil_court"
            l1 = self._lines_by_id[s1.lines[0]]
            l2 = self._lines_by_id[s2.lines[0]]
            if interchange in l1.stations and interchange in l2.stations:
                hop1 = abs(l1.stations.index(station1_id) - l1.stations.index(interchange))
                hop2 = abs(l2.stations.index(station2_id) - l2.stations.index(interchange))
                station_hop_count = hop1 + hop2

        # Map to fare slabs
        for slab in sorted(self.data.fare_rules.slabs, key=lambda x: x.max_stations):
            if station_hop_count <= slab.max_stations:
                return slab.fare_inr

        return self.data.fare_rules.slabs[-1].fare_inr


default_metro_adapter = MetroAdapter()
