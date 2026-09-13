"""Invariant and privacy tests for bounded OBS mix provenance."""

from dataclasses import FrozenInstanceError

import pytest

from utterleaf.obs_mix import (
    BusLabel,
    MAX_LABEL_BYTES,
    MAX_SOURCE_NAME_BYTES,
    MAX_SOURCES,
    MixMetadataError,
    MixRelationship,
    MixSnapshot,
    SourceAssignment,
)


PRIMARY = b"primary-source!!"
GUEST = b"guest-source-000"


class IntSubclass(int):
    pass


class StrSubclass(str):
    pass


class BytesSubclass(bytes):
    pass


def source(source_id=PRIMARY, name="Complete mix", bus_mask=0b001):
    return SourceAssignment(source_id, name, bus_mask)


def snapshot(*, primary=0, mask=0b111, sources=(), names=("Stream", "Guest", "Archive")):
    labels = tuple(BusLabel(bus, name) for bus, name in zip(range(6), names) if mask & (1 << bus))
    return MixSnapshot(primary, mask, tuple(sources), labels)


def test_snapshot_is_frozen_and_queries_selected_bus_assignments():
    complete = source(bus_mask=0b011)
    guest = source(GUEST, "Guest 🎧", 0b110)
    mixes = snapshot(sources=(guest, complete))

    assert mixes.inputs_for_bus(0) == (complete,)
    assert mixes.inputs_for_bus(1) == (guest, complete)
    assert mixes.inputs_for_bus(2) == (guest,)
    with pytest.raises(FrozenInstanceError):
        mixes.primary_bus = 1
    with pytest.raises(FrozenInstanceError):
        complete.name = "changed"


def test_invalid_metadata_uses_one_generic_public_error():
    with pytest.raises(MixMetadataError, match="^Invalid OBS mix metadata$") as caught:
        SourceAssignment(PRIMARY, "private\nname", 1)
    assert "private" not in str(caught.value)


def test_relationship_uses_only_exact_source_id_sets():
    sources = (
        source(GUEST, "Same display name", 0b100),
        source(PRIMARY, "Same display name", 0b011),
    )
    mixes = snapshot(mask=0b1111, sources=sources, names=("P", "Copy", "Other", "Empty"))

    assert mixes.relationship(0) is MixRelationship.PRIMARY
    assert mixes.relationship(1) is MixRelationship.SAME_INPUTS
    assert mixes.relationship(2) is MixRelationship.DIFFERENT_INPUTS
    assert mixes.relationship(3) is MixRelationship.UNASSIGNED


def test_two_unassigned_selected_buses_are_unassigned():
    mixes = snapshot(primary=0, mask=0b011, names=("Main", "Spare"))

    assert mixes.inputs_for_bus(0) == ()
    assert mixes.inputs_for_bus(1) == ()
    assert mixes.relationship(0) is MixRelationship.PRIMARY
    assert mixes.relationship(1) is MixRelationship.UNASSIGNED


@pytest.mark.parametrize(
    "source_id,name,bus_mask",
    [
        (b"short", "name", 1),
        (bytearray(16), "name", 1),
        (PRIMARY, "", 1),
        (PRIMARY, "x" * (MAX_SOURCE_NAME_BYTES + 1), 1),
        (PRIMARY, "name", 0),
        (PRIMARY, "name", 64),
        (PRIMARY, "name", True),
    ],
)
def test_source_assignment_rejects_inexact_or_unbounded_data(source_id, name, bus_mask):
    with pytest.raises(ValueError, match="^Invalid OBS mix metadata$"):
        SourceAssignment(source_id, name, bus_mask)


def test_primitive_subclasses_are_rejected():
    with pytest.raises(ValueError):
        SourceAssignment(BytesSubclass(PRIMARY), "name", 1)
    with pytest.raises(ValueError):
        SourceAssignment(PRIMARY, StrSubclass("name"), 1)
    with pytest.raises(ValueError):
        SourceAssignment(PRIMARY, "name", IntSubclass(1))
    with pytest.raises(ValueError):
        BusLabel(IntSubclass(0), "Main")
    with pytest.raises(ValueError):
        MixSnapshot(IntSubclass(0), 1, (), (BusLabel(0, "Main"),))


@pytest.mark.parametrize(
    "text",
    [
        "line\nbreak",
        "delete\x7f",
        "control\x85",
        "arabic mark\u061c",
        "zero width space\u200b",
        "left-to-right mark\u200e",
        "right-to-left mark\u200f",
        "separator\u2028",
        "paragraph\u2029",
        "embed\u202a",
        "override\u202e",
        "isolate\u2066",
        "pop isolate\u2069",
        "byte-order mark\ufeff",
        "\ud800",
    ],
)
def test_display_text_rejects_control_and_bidirectional_formatting(text):
    with pytest.raises(ValueError, match="^Invalid OBS mix metadata$"):
        SourceAssignment(PRIMARY, text, 1)
    with pytest.raises(ValueError, match="^Invalid OBS mix metadata$"):
        BusLabel(0, text)


@pytest.mark.parametrize("text", ["", " ", "\u00a0", "\u200c", "\u200d", " \u200c\u200d "])
def test_display_text_rejects_whitespace_or_joiners_without_visible_text(text):
    with pytest.raises(MixMetadataError, match="^Invalid OBS mix metadata$"):
        SourceAssignment(PRIMARY, text, 1)
    with pytest.raises(MixMetadataError, match="^Invalid OBS mix metadata$"):
        BusLabel(0, text)


def test_display_text_bounds_and_preserves_unicode_joiners_and_spacing():
    label = BusLabel(0, "👩\u200d💻 Mix")
    assignment = SourceAssignment(PRIMARY, "  می\u200cکروفن  ", 1)
    assert label.label == "👩\u200d💻 Mix"
    assert assignment.name == "  می\u200cکروفن  "

    with pytest.raises(ValueError):
        BusLabel(0, "🌿" * (MAX_LABEL_BYTES // 4 + 1))
    with pytest.raises(ValueError):
        SourceAssignment(PRIMARY, "🌿" * (MAX_SOURCE_NAME_BYTES // 4 + 1), 1)


@pytest.mark.parametrize("bus,label", [(True, "Main"), (6, "Main"), (0, ""), (0, b"Main")])
def test_bus_label_rejects_inexact_bus_or_text(bus, label):
    with pytest.raises(ValueError, match="^Invalid OBS mix metadata$"):
        BusLabel(bus, label)


@pytest.mark.parametrize(
    "primary,mask,sources,labels",
    [
        (True, 1, (), (BusLabel(0, "Main"),)),
        (0, True, (), (BusLabel(0, "Main"),)),
        (0, 0, (), ()),
        (1, 1, (), (BusLabel(0, "Main"),)),
        (0, 1, [], (BusLabel(0, "Main"),)),
        (0, 1, (), [BusLabel(0, "Main")]),
        (0, 0b11, (), (BusLabel(0, "Main"),)),
        (0, 0b11, (), (BusLabel(1, "Other"), BusLabel(0, "Main"))),
    ],
)
def test_snapshot_rejects_inexact_empty_or_incomplete_selection(primary, mask, sources, labels):
    with pytest.raises(ValueError, match="^Invalid OBS mix metadata$"):
        MixSnapshot(primary, mask, sources, labels)


def test_snapshot_rejects_more_than_six_labels():
    labels = tuple(BusLabel(0, f"Label {index}") for index in range(7))

    with pytest.raises(MixMetadataError, match="^Invalid OBS mix metadata$"):
        MixSnapshot(0, 1, (), labels)


def test_snapshot_requires_sorted_unique_ids_and_selected_source_masks():
    first = source(b"0000000000000001", "First", 0b01)
    second = source(b"0000000000000002", "Second", 0b10)
    labels = (BusLabel(0, "Main"), BusLabel(1, "Other"))

    with pytest.raises(ValueError):
        MixSnapshot(0, 0b11, (second, first), labels)
    with pytest.raises(ValueError):
        MixSnapshot(0, 0b11, (first, first), labels)
    with pytest.raises(ValueError):
        MixSnapshot(0, 0b01, (second,), (labels[0],))


def test_snapshot_caps_sources_at_128():
    sources = tuple(
        source(index.to_bytes(16, "big"), f"Input {index}", 1)
        for index in range(MAX_SOURCES + 1)
    )
    with pytest.raises(ValueError):
        snapshot(mask=1, sources=sources, names=("Main",))


def test_exact_text_and_source_count_bounds_are_accepted():
    sources = tuple(
        source(index.to_bytes(16, "big"), "n" * MAX_SOURCE_NAME_BYTES, 1)
        for index in range(MAX_SOURCES)
    )
    mixes = MixSnapshot(
        0,
        1,
        sources,
        (BusLabel(0, "l" * MAX_LABEL_BYTES),),
    )

    assert len(mixes.sources) == MAX_SOURCES
    assert len(mixes.labels[0].label.encode("utf-8")) == MAX_LABEL_BYTES


@pytest.mark.parametrize("bus", [1, -1, 6, True, 0.0])
def test_nonselected_or_inexact_bus_queries_are_rejected(bus):
    mixes = snapshot(mask=1, names=("Main",))
    with pytest.raises(ValueError, match="^Invalid OBS mix metadata$"):
        mixes.inputs_for_bus(bus)
    with pytest.raises(ValueError, match="^Invalid OBS mix metadata$"):
        mixes.relationship(bus)


def test_representations_hide_source_ids_and_all_display_text():
    assignment = source(PRIMARY, "Private input", 0b11)
    label = BusLabel(0, "Private bus")
    mixes = MixSnapshot(0, 0b11, (assignment,), (label, BusLabel(1, "Also private")))

    rendered = " ".join((repr(assignment), repr(label), repr(mixes)))
    assert "primary-source" not in rendered
    assert "Private" not in rendered
    assert "Also private" not in rendered
