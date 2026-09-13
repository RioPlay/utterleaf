"""Bounded immutable provenance for selected OBS audio mixes.

The model records OBS-provided assignments only.  It does not infer speakers or
inspect PCM, and identifiers and display text stay out of representations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


MAX_SOURCES = 128
MAX_LABEL_BYTES = 64
MAX_SOURCE_NAME_BYTES = 128

_MAX_BUS = 5
_MAX_BUS_MASK = 0x3F
_INVALID = "Invalid OBS mix metadata"


class MixMetadataError(ValueError):
    """OBS mix provenance violates the bounded domain contract."""


class MixRelationship(str, Enum):
    PRIMARY = "primary"
    SAME_INPUTS = "same_inputs"
    DIFFERENT_INPUTS = "different_inputs"
    UNASSIGNED = "unassigned"


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _bounded_text(value: object, maximum_bytes: int) -> bool:
    if type(value) is not str or not 0 < len(value) <= maximum_bytes:
        return False
    has_visible_text = False
    for character in value:
        codepoint = ord(character)
        if (
            codepoint <= 0x1F
            or codepoint == 0x061C
            or 0x7F <= codepoint <= 0x9F
            or codepoint == 0x200B
            or 0x200E <= codepoint <= 0x200F
            or 0x2028 <= codepoint <= 0x202E
            or 0x2066 <= codepoint <= 0x2069
            or codepoint == 0xFEFF
        ):
            return False
        if not character.isspace() and codepoint not in (0x200C, 0x200D):
            has_visible_text = True
    if not has_visible_text:
        return False
    try:
        return len(value.encode("utf-8")) <= maximum_bytes
    except UnicodeEncodeError:
        return False


@dataclass(frozen=True, slots=True)
class SourceAssignment:
    source_id: bytes = field(repr=False)
    name: str = field(repr=False)
    bus_mask: int

    def __post_init__(self) -> None:
        if (
            type(self.source_id) is not bytes
            or len(self.source_id) != 16
            or not _bounded_text(self.name, MAX_SOURCE_NAME_BYTES)
            or not _integer(self.bus_mask, 1, _MAX_BUS_MASK)
        ):
            raise MixMetadataError(_INVALID)


@dataclass(frozen=True, slots=True)
class BusLabel:
    bus: int
    label: str = field(repr=False)

    def __post_init__(self) -> None:
        if not _integer(self.bus, 0, _MAX_BUS) or not _bounded_text(
            self.label, MAX_LABEL_BYTES
        ):
            raise MixMetadataError(_INVALID)


@dataclass(frozen=True, slots=True)
class MixSnapshot:
    primary_bus: int
    bus_mask: int
    sources: tuple[SourceAssignment, ...]
    labels: tuple[BusLabel, ...]

    def __post_init__(self) -> None:
        if (
            not _integer(self.primary_bus, 0, _MAX_BUS)
            or not _integer(self.bus_mask, 1, _MAX_BUS_MASK)
            or not self.bus_mask & (1 << self.primary_bus)
            or type(self.sources) is not tuple
            or not len(self.sources) <= MAX_SOURCES
            or any(type(source) is not SourceAssignment for source in self.sources)
            or type(self.labels) is not tuple
            or len(self.labels) > _MAX_BUS + 1
            or any(type(label) is not BusLabel for label in self.labels)
        ):
            raise MixMetadataError(_INVALID)

        source_ids = tuple(source.source_id for source in self.sources)
        selected_buses = tuple(
            bus for bus in range(_MAX_BUS + 1) if self.bus_mask & (1 << bus)
        )
        if (
            source_ids != tuple(sorted(source_ids))
            or len(source_ids) != len(set(source_ids))
            or any(source.bus_mask & ~self.bus_mask for source in self.sources)
            or tuple(label.bus for label in self.labels) != selected_buses
        ):
            raise MixMetadataError(_INVALID)

    def inputs_for_bus(self, bus: int) -> tuple[SourceAssignment, ...]:
        self._check_selected_bus(bus)
        bit = 1 << bus
        return tuple(source for source in self.sources if source.bus_mask & bit)

    def relationship(self, bus: int) -> MixRelationship:
        self._check_selected_bus(bus)
        if bus == self.primary_bus:
            return MixRelationship.PRIMARY
        primary_ids = {
            source.source_id
            for source in self.sources
            if source.bus_mask & (1 << self.primary_bus)
        }
        bus_ids = {
            source.source_id
            for source in self.sources
            if source.bus_mask & (1 << bus)
        }
        if not bus_ids:
            return MixRelationship.UNASSIGNED
        if primary_ids == bus_ids:
            return MixRelationship.SAME_INPUTS
        return MixRelationship.DIFFERENT_INPUTS

    def _check_selected_bus(self, bus: int) -> None:
        if not _integer(bus, 0, _MAX_BUS) or not self.bus_mask & (1 << bus):
            raise MixMetadataError(_INVALID)


__all__ = [
    "BusLabel",
    "MAX_LABEL_BYTES",
    "MAX_SOURCE_NAME_BYTES",
    "MAX_SOURCES",
    "MixMetadataError",
    "MixRelationship",
    "MixSnapshot",
    "SourceAssignment",
]
