import pytest

from utterleaf.dictation_spacing import prepare_delivery
from utterleaf.polish import stitch_to_previous


@pytest.mark.parametrize("first,second", [
    ("Bring it to the front.", "Just little nitpicks."),
    ("What's causing that.", "Guess you can literally see it."),
])
@pytest.mark.parametrize("context_retained", [False, True])
def test_separate_takes_keep_sentence_boundary(first, second, context_retained):
    first_delivery = prepare_delivery(first)
    # Expired (>20 s) or changed-title context is represented by no previous payload.
    second_delivery = prepare_delivery(
        second, previous_delivered=first_delivery.payload if context_retained else "")
    assert first_delivery.payload + second_delivery.payload == first + " " + second + " "


@pytest.mark.parametrize("text", ["Wait!", "Why?", 'He said "yes."', "Done.)"])
def test_sentence_completion_has_receiptable_separator(text):
    delivery = prepare_delivery(text)
    assert delivery.payload == delivery.prefix + delivery.text + delivery.suffix
    assert delivery.suffix == " "
    assert len(delivery.payload) == len(text) + 1


def test_unfinished_take_does_not_put_space_before_stitch_period():
    first = prepare_delivery("Hello")
    second = prepare_delivery("Next.", previous_delivered=first.payload)
    assert first.payload + second.payload == "Hello. Next. "


@pytest.mark.parametrize("text", ["", " \t", "\n", "First.\n", "First.\n\t", "- One.\n- Two."])
def test_explicit_layout_is_unchanged(text):
    assert prepare_delivery(text).payload == text


@pytest.mark.parametrize("options", [{"text_cleanup": False}, {"code_mode": True}])
def test_literal_and_code_unchanged(options):
    text = "  example.foo()!\n"
    assert prepare_delivery(text, previous_delivered="Old.", **options).payload == text


@pytest.mark.parametrize("previous", ["Before.\n", "Before\n\t", "Before.\r\n"])
def test_stitch_preserves_existing_newline(previous):
    assert stitch_to_previous(previous, "next.") == "Next."


@pytest.mark.parametrize("command", ["bullets", "numbered", "paragraph", "newline"])
def test_structured_commands_keep_existing_join_policy(command):
    delivery = prepare_delivery("One.\n", previous_delivered="Before.", command=command)
    assert delivery.payload == "\nOne.\n"
    assert delivery.suffix == ""


@pytest.mark.parametrize("command", ["discard", "replace"])
def test_non_insert_commands_are_not_padded(command):
    assert prepare_delivery("Replacement.", command=command).payload == "Replacement."


@pytest.mark.parametrize("command", [None, "bullets", "numbered"])
def test_prose_after_list_keeps_next_take_separate_after_context_expires(command):
    first = prepare_delivery("- Cats\n- Dogs\n\nBack to prose.", command=command)
    second = prepare_delivery("Another take.")
    assert first.payload + second.payload == "- Cats\n- Dogs\n\nBack to prose. Another take. "


def test_multiline_prose_keeps_internal_breaks_and_both_take_boundaries():
    delivery = prepare_delivery("Cats.\nDogs.", previous_delivered="Before.")
    assert delivery.payload == " Cats.\nDogs. "
    assert delivery.text == "Cats.\nDogs."
