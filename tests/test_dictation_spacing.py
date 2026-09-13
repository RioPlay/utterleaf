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


@pytest.mark.parametrize("command, text", [
    ("bullets", "- Apples\n- Pears"),
    ("numbered", "1. Apples\n2. Pears"),
])
def test_completed_explicit_list_ends_before_following_text(command, text):
    delivery = prepare_delivery(text, command=command)
    # Model the caret between existing words. The separator belongs to this
    # verified payload, so both a later take and text right of the caret stay
    # outside the final list item without reading the destination editor.
    next_take = prepare_delivery("Next sentence.", previous_delivered=delivery.payload)
    assert delivery.payload + next_take.payload == text + "\nNext sentence. "
    assert "Before " + delivery.payload + "after" == "Before " + text + "\nafter"


@pytest.mark.parametrize("first, second", [
    ('Hello.', '"Next sentence."'),
    ('He said "yes."', "Then left."),
])
def test_completed_prose_takes_keep_one_separator_at_caret(first, second):
    first_delivery = prepare_delivery(first)
    second_delivery = prepare_delivery(second, previous_delivered=first_delivery.payload)
    assert first_delivery.payload + second_delivery.payload == first + " " + second + " "
    assert "Before " + first_delivery.payload + "after" == "Before " + first + " after"


def test_native_neighbors_add_only_required_word_boundaries():
    assert prepare_delivery("Hello.", neighbors=("e", "a")).payload == " Hello. "
    assert prepare_delivery("Hello.", neighbors=(" ", ",")).payload == "Hello"
    assert prepare_delivery("- One", command="bullets", neighbors=("e", "a")).payload == "\n- One\n"
    assert prepare_delivery("- One", command="bullets", neighbors=(" ", "a")).payload == "\n- One\n"


def test_native_neighbors_do_not_change_literal_or_code_delivery():
    assert prepare_delivery("x.y", text_cleanup=False, neighbors=("e", "a")).payload == "x.y"
    assert prepare_delivery("x.y", code_mode=True, neighbors=("e", "a")).payload == "x.y"


def test_empty_native_field_keeps_a_separator_for_an_expired_next_take():
    first = prepare_delivery("Hello.", neighbors=("", ""))
    second = prepare_delivery("Next.", neighbors=(".", ""))
    assert first.payload + second.payload == "Hello. Next. "


@pytest.mark.parametrize("after", ["", " ", ","])
def test_list_block_delimiter_survives_native_right_context(after):
    delivery = prepare_delivery("- Apples\n- Pears", command="bullets", neighbors=("e", after))
    assert delivery.payload == "\n- Apples\n- Pears\n"


def test_markdown_heading_and_list_have_commonmark_take_boundaries():
    heading = prepare_delivery("## Project notes", command="heading", markdown=True)
    follow = prepare_delivery("Next sentence.", previous_delivered=heading.payload)
    assert heading.payload + follow.payload == "## Project notes\n\nNext sentence. "
    listing = prepare_delivery("- Apples\n- Pears", command="bullets", markdown=True)
    assert listing.payload == "- Apples\n- Pears\n\n"


def test_markdown_blocks_do_not_accumulate_extra_breaks_between_takes():
    heading = prepare_delivery("## Project notes", command="heading", markdown=True)
    listing = prepare_delivery("- Apples", previous_delivered=heading.payload,
                               command="bullets", markdown=True)
    next_listing = prepare_delivery("- Pears", previous_delivered=listing.payload,
                                    command="bullets", markdown=True)
    prose = prepare_delivery("Next sentence.", previous_delivered=next_listing.payload)
    assert heading.payload + listing.payload + next_listing.payload + prose.payload == (
        "## Project notes\n\n- Apples\n\n- Pears\n\nNext sentence. "
    )


def test_native_right_delimiters_do_not_duplicate_inferred_full_stop():
    assert "Hello" + prepare_delivery("World.", neighbors=("o", ".")).payload + "." == "Hello World."
    assert "Hello" + prepare_delivery("Hello.", neighbors=("o", ",")).payload + "," == "Hello Hello,"


@pytest.mark.parametrize(("after", "expected"), [(")", "Hello."), ('"', "Hello. "), ("!", "Hello.")])
def test_native_right_quotes_parentheses_and_exclamation_keep_punctuation(after, expected):
    assert prepare_delivery("Hello.", neighbors=("(", after)).payload == expected
