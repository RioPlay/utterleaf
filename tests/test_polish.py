from utterleaf.polish import COMMAND_HINT, infer_style, polish_local
import pytest


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
