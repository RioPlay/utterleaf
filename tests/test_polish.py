from utterleaf.polish import COMMAND_HINT, infer_style, polish_local
import pytest


@pytest.mark.parametrize("raw", [
    "um I mean scratch that", "  make a list one two three  ",
    "je veux garder ça, new paragraph", "i use a p i dot py", " utter leaf\n",
])
def test_cleanup_off_preserves_model_transcript_exactly(raw):
    result = polish_local(raw, vocab=[("utter leaf", "Utterleaf")], app_name="terminal",
                          text_cleanup=False)
    assert result.text == raw
    assert not result.command_only
    assert not result.discarded
    assert result.command is None


@pytest.mark.parametrize("phrase", [
    "make a bulleted list one two three",
    "Make a bulleted list: one two three.",
    "make a bolded list one two three",
    "make a bullet list of one, two, and three.",
])
def test_spoken_bullet_list_variants(phrase):
    result = polish_local(phrase, vocab=[])
    assert result.command == "bullets"
    assert result.text == "- One\n- Two\n- Three"


@pytest.mark.parametrize("phrase, expected", [
    ("Make a bulleted list olive oil, coffee beans, and paper towels.",
     "- Olive oil\n- Coffee beans\n- Paper towels"),
    ("Make a bulleted list research and development, first aid supplies, and delivery dates.",
     "- Research and development\n- First aid supplies\n- Delivery dates"),
    ("Make a bulleted list bullet point research and development next bullet point first aid supplies end list That is all.",
     "- Research and development\n- First aid supplies\n\nThat is all."),
])
def test_explicit_list_boundaries_preserve_multiword_items(phrase, expected):
    assert polish_local(phrase, vocab=[]).text == expected


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("command, marker", [("bulleted", "-"), ("numbered", None)])
def test_explicit_list_newlines_override_word_and_punctuation_heuristics(newline, command, marker):
    items = ["Olive oil", "Research and development", "First aid supplies", "Paris, France"]
    raw = f"Make a {command} list: " + newline.join(items)
    result = polish_local(raw, vocab=[])
    assert result.command == ("bullets" if marker else "numbered")
    assert result.text.splitlines() == [
        f"{marker or str(index) + '.'} {item}" for index, item in enumerate(items, 1)
    ]


def test_edit_existing_lines_as_list_ignores_blank_lines_and_keeps_item_phrases():
    from utterleaf.polish import apply_edit

    assert apply_edit("  Olive oil\r\n\r\n Research and development \r\n First aid supplies  ", "bullets") == (
        "- Olive oil\n- Research and development\n- First aid supplies"
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("items, expected", [
    (["bullet point cats", "next bullet point dogs"], "- Cats\n- Dogs"),
    (["bullet point: research and development", "next bullet point first aid supplies", "Discuss the bullet point design"],
     "- Research and development\n- First aid supplies\n- Discuss the bullet point design"),
])
def test_explicit_list_lines_remove_only_leading_spoken_bullet_markers(newline, items, expected):
    raw = "Make a bulleted list " + newline.join(items) + " end list Back to prose."
    result = polish_local(raw, vocab=[])
    assert result.text == expected + "\n\nBack to prose."
    assert result.command == "bullets"


def test_lines_without_explicit_list_command_remain_prose():
    raw = "Cats\nDogs\nCars\nElephants\nOr New Line. Alright\nNow I'm just talking into a paragraph again."
    result = polish_local(raw, vocab=[])
    assert result.command is None
    assert result.text == raw


@pytest.mark.parametrize("options", [{"text_cleanup": False}, {"app_name": "code.exe"}])
def test_multiline_list_request_does_not_format_literal_or_code(options):
    raw = "Make a bulleted list: Olive oil\nResearch and development\nFirst aid supplies"
    result = polish_local(raw, vocab=[], **options)
    assert result.command is None
    assert result.text == raw


@pytest.mark.parametrize("raw, expected", [
    ("Cats. New line. Dogs. New paragraph. Prose.", "Cats.\nDogs.\n\nProse."),
    ("Cats\nNew line\nDogs\nNew paragraph\nProse.", "Cats\nDogs\n\nProse."),
    ("Cats\r\nNew line\r\nDogs\r\nNew paragraph\r\nProse.", "Cats\nDogs\n\nProse."),
    ("Cats. New line! Dogs. NEW PARAGRAPH? Prose.", "Cats.\nDogs.\n\nProse."),
    ("New line. You are welcome.", "\nYou are welcome."),
    ("Cats. New line. You. New paragraph. More prose.", "Cats.\nYou.\n\nMore prose."),
    ("Cats. New line. New line. Dogs.", "Cats.\n\nDogs."),
    ("Cats. New paragraph. New paragraph. Dogs.", "Cats.\n\nDogs."),
])
def test_inline_break_commands_have_strict_boundaries_and_no_edit_metadata(raw, expected):
    result = polish_local(raw, vocab=[])
    assert result.text == expected
    assert result.command is None
    assert not result.command_only and not result.discarded


@pytest.mark.parametrize("raw", [
    'She said "New line. New paragraph." Then continued.',
    "She said ‘New line. New paragraph.’ Then continued.",
    "The example is `New line. New paragraph.` Keep it literal.",
    "I said new line. Then continued.",
    "Say: new paragraph. Then continue.",
    "Start a new line. Then continue.",
    "A new line of business. A new paragraph about sales.",
    "Cats new line Dogs new paragraph More prose.",
    "Or New Line. Alright\nNow I'm just talking into a paragraph again.",
])
def test_inline_break_references_and_ambiguous_speech_stay_literal(raw):
    result = polish_local(raw, vocab=[])
    assert result.text == raw
    assert result.command is None


@pytest.mark.parametrize("options", [{"text_cleanup": False}, {"app_name": "code.exe"}])
def test_inline_break_commands_do_not_run_in_literal_or_code_modes(options):
    raw = "Cats. New line. Dogs. New paragraph. More prose. You."
    result = polish_local(raw, vocab=[], **options)
    # Code mode's existing path punctuation removes spaces after dots; it must
    # still retain the spoken command words and add no line/paragraph breaks.
    assert result.text == (raw if options.get("text_cleanup") is False else raw.replace(". ", "."))
    assert result.command is None


def test_inline_break_reference_guard_uses_original_context_after_earlier_command():
    result = polish_local('Cats. New line. She said:\nNew paragraph\nThen wrote "New line."', vocab=[])
    assert result.text == 'Cats.\nShe said:\nNew paragraph\nThen wrote "New line.".'
    assert result.command is None


@pytest.mark.parametrize("phrase, command, expected", [
    ("New line.", "newline", "\n"),
    ("New paragraph.", "paragraph", "\n\n"),
    ("Cats new line.", "newline", "Cats\n"),
    ("Cats new paragraph.", "paragraph", "Cats\n\n"),
])
def test_standalone_and_trailing_break_command_semantics_unchanged(phrase, command, expected):
    result = polish_local(phrase, vocab=[])
    assert result.text == expected
    assert result.command == command
    assert result.command_only == phrase.lower().startswith("new ")


def test_inline_breaks_preserve_explicit_end_list_transition():
    result = polish_local("Make a bulleted list: Olive oil. New line. Research and development. "
                          "New line. First aid supplies. End list. More prose. New paragraph. Final thought.", vocab=[])
    assert result.text == "- Olive oil\n- Research and development\n- First aid supplies\n\nMore prose.\n\nFinal thought."
    assert result.command == "bullets"


def test_inline_break_does_not_guess_end_of_explicit_list():
    result = polish_local("Make a bulleted list: Cats. New line. Dogs. New paragraph. More prose.", vocab=[])
    assert result.text == "- Cats\n- Dogs\n- More prose"
    assert result.command == "bullets"


@pytest.mark.parametrize("phrase", ["make a bulleted list 1 2 3.", "make a bolded list 1, 2, 3."])
def test_digit_list_from_recognizer(phrase):
    assert polish_local(phrase, vocab=[]).text == "- 1\n- 2\n- 3"


def test_list_embedded_in_users_continuing_dictation():
    phrase = ("And now I'm just gonna say make a bolded list one two three just because "
              "I'm testing that as I write this to you. Yeah, there is no bulleted list.")
    result = polish_local(phrase, vocab=[])
    assert "- One\n- Two\n- Three" in result.text
    assert "And now I'm just gonna say" in result.text
    assert "Just because I'm testing that as I write this to you." in result.text
    assert "there is no bulleted list" in result.text
    assert "make a bolded list" not in result.text


def test_end_list_preserves_following_prose():
    result = polish_local("Here is the plan. Make a bulleted list first open the ticket "
                          "second assign it third close it end list That is all.", vocab=[])
    assert result.text == "Here is the plan.\n\n- Open the ticket\n- Assign it\n- Close it\n\nThat is all."


@pytest.mark.parametrize("phrase, command", [
    ("Make this a bulleted list.", "bullets"),
    ("Make this a bolded list!", "bullets"),
    ("Make this shorter.", "shorter"),
    ("Scratch that.", "discard"),
])
def test_command_only_accepts_recognizer_punctuation(phrase, command):
    result = polish_local(phrase)
    assert result.command == command
    assert result.command_only


def test_numbered_list_prefix_keeps_numbered_style():
    assert polish_local("Make a numbered list one two three.", vocab=[]).text == "1. One\n2. Two\n3. Three"


@pytest.mark.parametrize("phrase", ["This is a bolded heading.", "We made a bulleted list yesterday.", "A new line of business."])
def test_ordinary_list_mentions_remain_prose(phrase):
    result = polish_local(phrase, vocab=[])
    assert result.command is None
    assert result.text == phrase


def test_removes_fillers() -> None:
    result = polish_local("um I think we should, uh, ship it today")
    assert "um" not in result.text.lower()
    assert "uh" not in result.text.lower()
    assert "ship it today" in result.text.lower()
    assert ", ship" not in result.text.lower()


def test_self_correction_keeps_final_intent() -> None:
    result = polish_local("send it to John no wait send it to Sarah")
    assert "john" not in result.text.lower()
    assert "sarah" in result.text.lower()


def test_sorry_as_apology_is_kept() -> None:
    result = polish_local("I'm sorry I was late")
    assert "sorry" in result.text.lower()
    assert "late" in result.text.lower()


def test_i_mean_correction() -> None:
    result = polish_local("the meeting is at three I mean four")
    assert "four" in result.text.lower()
    assert "three" not in result.text.lower()


def test_repeated_word() -> None:
    result = polish_local("the the meeting starts now")
    assert "the the" not in result.text.lower()


def test_scratch_that_discards() -> None:
    result = polish_local("hello world scratch that")
    assert result.discarded
    assert result.text == ""


def test_scratch_that_alone() -> None:
    result = polish_local("scratch that")
    assert result.discarded
    assert result.command_only


def test_was_a_list_is_not_a_command() -> None:
    result = polish_local("this was a list")
    assert result.command is None
    assert "this was a list" in result.text.lower()


def test_new_line_of_business_is_not_a_command() -> None:
    result = polish_local("new line of business")
    assert result.command is None
    assert "business" in result.text.lower()


def test_bulleted_list_from_speech() -> None:
    result = polish_local("eggs milk and bread as a bulleted list")
    assert result.command == "bullets"
    assert result.text.splitlines() == ["- Eggs", "- Milk", "- Bread"]


def test_make_a_list_of_prefix() -> None:
    result = polish_local("make a list of eggs, milk, and bread")
    assert result.command == "bullets"
    assert "- Eggs" in result.text
    assert "- Bread" in result.text


def test_numbered_first_second_third() -> None:
    result = polish_local(
        "first open the ticket second assign it third close it as a numbered list"
    )
    assert result.command == "numbered"
    lines = result.text.splitlines()
    assert lines[0].startswith("1. ")
    assert "Open the ticket" in lines[0]
    assert lines[2].startswith("3. ")


def test_kind_of_stays() -> None:
    result = polish_local("it's kind of urgent")
    assert "kind of" in result.text.lower()
    assert "urgent" in result.text.lower()


def test_i_mean_it_is_kept() -> None:
    result = polish_local("I mean it")
    assert "mean" in result.text.lower()
    assert "it" in result.text.lower()


def test_list_command_only() -> None:
    result = polish_local("make this a bulleted list")
    assert result.command_only
    assert result.command == "bullets"


def test_new_paragraph() -> None:
    result = polish_local("first thought new paragraph")
    assert result.text.endswith("\n\n")
    assert "first thought" in result.text.lower()


def test_vocabulary_replacement() -> None:
    result = polish_local("call the manager later", vocab=[("the manager", "The Manager")])
    assert "The Manager" in result.text


def test_make_this_shorter_strips_hedges() -> None:
    result = polish_local(
        "I think we should probably just ship the patch today make this shorter"
    )
    assert result.command == "shorter"
    assert "probably" not in result.text.lower()
    assert "ship" in result.text.lower()


def test_make_it_more_professional() -> None:
    result = polish_local("yeah I'm gonna send that later make it more professional")
    assert result.command == "professional"
    assert "gonna" not in result.text.lower()
    assert "going to" in result.text.lower()


def test_code_style_skips_forced_period_on_short() -> None:
    result = polish_local("git status", app_name="Code.exe Visual Studio Code")
    assert infer_style("Code.exe Visual Studio Code") == "code"
    assert result.text.lower().startswith("git")


def test_codex_is_not_mistaken_for_code_editor() -> None:
    result = polish_local("The first sentence.The second sentence", app_name="Codex.exe")
    assert infer_style("Codex.exe") == "default"
    assert result.text == "The first sentence. The second sentence."


def test_browser_article_about_code_is_not_code_mode() -> None:
    result = polish_local(
        "The first sentence.The second sentence",
        app_name="chrome.exe — How to write better code",
    )
    assert infer_style("chrome.exe — How to write better code") == "default"
    assert result.text == "The first sentence. The second sentence."


def test_spoken_punctuation() -> None:
    result = polish_local("ship it today period then ping me question mark")
    assert "today." in result.text
    assert result.text.endswith("?")


def test_period_of_time_is_kept() -> None:
    result = polish_local("we need a period of time to test")
    assert "period of time" in result.text.lower()


def test_standalone_i_is_capitalized() -> None:
    result = polish_local("and then i will send it")
    assert " I " in result.text


def test_whisper_thanks_tail_is_stripped() -> None:
    result = polish_local("The patch is ready. Thank you.")
    assert "thank you" not in result.text.lower()
    assert "patch is ready" in result.text.lower()


def test_thank_you_alone_is_kept() -> None:
    result = polish_local("Thank you.")
    assert "thank you" in result.text.lower()


def test_question_gets_question_mark() -> None:
    result = polish_local("what API is this even getting sent to")
    assert result.text.endswith("?")
    assert result.text.startswith("What")


def test_short_sentence_gets_a_period() -> None:
    result = polish_local("this is very weird")
    assert result.text.endswith(".")


def test_missing_apostrophes() -> None:
    result = polish_local("it doesnt fix mistakes")
    assert "doesn't" in result.text


def test_there_and_where_get_distinct_apostrophes() -> None:
    assert polish_local("theres a problem", vocab=[]).text == "There's a problem."
    assert polish_local("wheres the problem", vocab=[]).text == "Where's the problem?"


def test_stitch_adds_period_between_takes() -> None:
    from utterleaf.polish import stitch_to_previous

    assert stitch_to_previous("It works pretty good", "Honestly I am not impressed") == (
        ". Honestly I am not impressed"
    )
    assert stitch_to_previous("It works pretty good.", "honestly I am not impressed") == (
        " Honestly I am not impressed"
    )


def test_stitch_first_take_has_no_prefix() -> None:
    from utterleaf.polish import stitch_to_previous

    assert stitch_to_previous("", "Here's a quick test.") == "Here's a quick test."


def test_space_after_period_inside_take() -> None:
    result = polish_local("Hello.World is here")
    assert "Hello. World" in result.text


def test_apostrophe_does_not_start_an_acronym_run() -> None:
    result = polish_local("There's a rounded corner on the left")
    assert result.text == "There's a rounded corner on the left."


def test_curly_apostrophe_does_not_start_an_acronym_run() -> None:
    result = polish_local("There’s a rounded corner on the left")
    assert result.text == "There’s a rounded corner on the left."


def test_ordinary_words_are_not_merged_as_a_letter_run() -> None:
    result = polish_local("I am a little tired")
    assert result.text == "I am a little tired."


def test_sentence_spacing_survives_adjacent_sentences() -> None:
    result = polish_local("The first sentence.The second sentence")
    assert result.text == "The first sentence. The second sentence."


def test_sentence_spacing_is_cased_before_final_cleanup() -> None:
    result = polish_local("The first sentence.the second sentence")
    assert result.text == "The first sentence. The second sentence."


def test_list_mention_in_planning_prose_stays_prose() -> None:
    result = polish_local("We need to make a list of things to fix")
    assert result.command is None
    assert result.text == "We need to make a list of things to fix."


def test_reported_list_command_stays_prose() -> None:
    result = polish_local("We can say make a list of things to fix")
    assert result.command is None
    assert result.text == "We can say make a list of things to fix."


@pytest.mark.parametrize("phrase", [
    "I can make a list of things to fix",
    "I said make a list of things to fix",
])
def test_reported_list_command_with_first_person_stays_prose(phrase: str) -> None:
    result = polish_local(phrase)
    assert result.command is None
    assert result.text == f"{phrase}."


def test_command_hint_lists_the_verbs() -> None:
    text = COMMAND_HINT.lower()
    assert "scratch that" in text
    assert "new line" in text
    assert "make a list" in text


@pytest.mark.parametrize("raw", ["Scratch, that.", "Scratch that!", "scratch, that,", "scratch that...", "Scratch,that."])
def test_scratch_pause_punctuation_discards(raw):
    result = polish_local(raw, vocab=[])
    assert result.discarded and result.command_only


@pytest.mark.parametrize("raw", [
    "scratch that, new information", "Scratch, that. New information",
    "scratch that: new information", "Scratch that! New information",
])
def test_leading_scratch_replacement_is_explicit_edit(raw):
    result = polish_local(raw, vocab=[])
    assert result.command == "replace"
    assert result.text == "New information."
    assert not result.discarded and not result.command_only


@pytest.mark.parametrize("raw", [
    'The words "scratch that" are a command',
    "The words 'scratch that' are a command",
    '"scratch that, new information"',
    'I said "scratch that"',
    'The words “scratch that” are a command',
])
def test_quoted_scratch_reference_stays_text(raw):
    result = polish_local(raw, vocab=[])
    assert result.command is None and not result.discarded
    assert "scratch that" in result.text.lower()


@pytest.mark.parametrize("raw", ["scratch, that", "scratch that, new information"])
def test_scratch_does_not_edit_code_or_literal(raw):
    literal = polish_local(raw, vocab=[], text_cleanup=False)
    code = polish_local(raw, vocab=[], app_name="code.exe")
    assert literal.text == raw and literal.command is None
    assert code.command is None and not code.discarded
    assert "scratch" in code.text


@pytest.mark.parametrize("raw", [
    "I said scratch that", "The command scratch that removes a take",
    "You can say scratch that, then continue", "The phrase scratch that is useful",
])
def test_reported_scratch_command_is_not_executed(raw):
    result = polish_local(raw, vocab=[])
    assert result.command is None and not result.discarded
    assert "scratch that" in result.text.lower()


def test_email_style_sentence_case() -> None:
    result = polish_local(
        "thanks for sending the report I will review it this afternoon",
        app_name="outlook",
    )
    assert result.text[0].isupper()
    assert result.text.endswith(".")


def test_windows_browser_title_is_not_code_identity() -> None:
    result = polish_local("there's a corner.the next sentence", app_name="chrome.exe How to write code - Google Chrome")
    assert result.text == "There's a corner. The next sentence."


def test_linux_editor_title_uses_application_suffix() -> None:
    from utterleaf.polish import infer_style

    assert infer_style("notes.txt - Visual Studio Code") == "code"
    assert infer_style("How to write code - Mozilla Firefox") != "code"
