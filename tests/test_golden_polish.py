import pytest
from utterleaf.polish import polish_local

# Format: (input_text, app_name, expected_text)
GOLDEN_CANDIDATES = [
    # Terminal / Code
    ("l s dash l a", "terminal", "ls -la"),
    ("git checkout dash b test dash new dash feature", "terminal", "git checkout -b test-new-feature"),
    ("git push origin main dash dash force", "terminal", "git push origin main --force"),
    ("n p m run test dash dash watch", "terminal", "NPM run test --watch"),
    ("grep dash r n todo dot py", "terminal", "grep -rn todo.py"),
    ("cat slash var slash log slash ship dash two dot text", "terminal", "cat/var/log/ship-two.text"),
    ("echo pipe tee note dot text", "terminal", "echo | tee note.text"),
    
    # Slack / Communication
    ("we should ship it soon", "slack", "We should ship it soon."),
    ("read the r f c first", "slack", "Read the RFC first."),
    ("add an s q l index to the users table", "slack", "Add an SQL index to the users table."),
    ("the sequel query is slow", "slack", "The SQL query is slow."),
]

@pytest.mark.parametrize("input_text, app, expected", GOLDEN_CANDIDATES)
def test_polish_golden(input_text, app, expected):
    result = polish_local(input_text, app_name=app)
    assert result.text == expected, f"Failed for {input_text} ({app}): expected {repr(expected)}, got {repr(result.text)}"
