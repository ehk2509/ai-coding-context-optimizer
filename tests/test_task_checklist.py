"""Tests for prompt-derived task coverage checklists."""

from acco.task_checklist import extract_task_checklist, task_checklist_note

SEABORN_LIKE = """Solve the historical software issue below.

--- HISTORICAL ISSUE ---
Wrong legend values of large ranges
```python
import seaborn as sns
import seaborn.objects as so

penguins = sns.load_dataset("Penguins")
(
    so.Plot(penguins, x="bill_length_mm", pointsize="body_mass_mg")
    .add(so.Dot())
)
```
which is wrong because `body_mass_mg` is in the order of 1E6. The issue also reproduces if you create the mentioned plot using `scatterplot`.

I believe the issue stems from https://github.com/example/blob/scales.py#L377
"""


_ISSUE = (
    "Legend values are wrong for large ranges: numbers in the order of 1E6 are "
    "shown without their multiplicative offset, so a legend reads 1, 2, 3 instead "
    "of 1e6, 2e6, 3e6. This makes plots of large-magnitude data misleading. "
)


def test_checklist_names_the_second_path_the_issue_mentions():
    items = extract_task_checklist(SEABORN_LIKE)
    assert items[0] == (
        "code example 1 from the task (calls sns.load_dataset, so.Plot, so.Dot)"
    )
    assert any("also reproduces" in item and "`scatterplot`" in item for item in items)
    assert not any("https://" in item for item in items)


def test_note_lists_items_and_demands_checking_each():
    note = task_checklist_note(SEABORN_LIKE)
    assert note.startswith("ACCO TASK CHECKLIST")
    assert "fixing one does not cover the others" in note
    assert "- code example 1" in note


def test_single_also_sentence_naming_a_new_api_counts_as_two_items():
    prompt = _ISSUE + "It shows in `so.Plot`.\n\nThe issue also reproduces with `scatterplot`."
    items = extract_task_checklist(prompt)
    assert items[0] == "the primary behaviour reported in the task"
    assert "`scatterplot`" in items[1]
    assert task_checklist_note(prompt) is not None


def test_another_symptom_of_the_same_option_is_not_a_separate_item():
    # pylint-6386: listing this pulled agents toward patching the help text
    # instead of the -v parsing (checklist on 2/5 vs off 4/5).
    prompt = (
        "The short option of the `verbose` option expects an argument.\n\n"
        "Also, the help message for the `verbose` option suggests a value `VERBOSE`."
    )
    assert extract_task_checklist(prompt) == []
    assert task_checklist_note(prompt) is None


def test_single_path_prompt_stays_silent():
    prompt = (
        "Request with binary payload fails.\n```\nimport requests\n"
        "requests.put('http://x', data=u'ööö'.encode('utf-8'))\n```\n"
        "This works with 2.8.1, but not with 2.9."
    )
    assert extract_task_checklist(prompt) == []
    assert task_checklist_note(prompt) is None


def test_tracebacks_and_repeated_examples_are_not_separate_items():
    prompt = (
        "```\nfits.Card('CONFIG', \"x''\")\nfits.Card.fromstring(str(card1))\n```\n"
        "```\nfits.Card('CONFIG', \"y''\")\nfits.Card.fromstring(str(card2))\n```\n"
        "```\nTraceback (most recent call last):\n  File \"x.py\", line 1, in f()\n```\n"
        "The same bug also affects `Header.parse`."
    )
    items = extract_task_checklist(prompt)
    assert sum(item.startswith("code example") for item in items) == 1
    assert len(items) == 2


def test_also_without_a_code_reference_is_ignored():
    assert extract_task_checklist("It is also slow. Please fix it.") == []


def test_call_reference_is_judged_by_its_function_name_not_its_arguments():
    # Review finding: `scatterplot(data=df)` used to be judged by `df`.
    prompt = (
        _ISSUE + "It happens in `so.Plot(df)`. "
        "The issue also reproduces with `scatterplot(data=df)`."
    )
    assert any("`scatterplot(data=df)`" in item for item in extract_task_checklist(prompt))


def test_uniqueness_counts_whole_words_only():
    # Review finding: "scatterplots" used to hide `scatterplot`.
    prompt = (
        _ISSUE + "Seen in scatterplots made with objects. "
        "The issue also reproduces with `scatterplot`."
    )
    assert any("`scatterplot`" in item for item in extract_task_checklist(prompt))


def test_short_follow_ups_and_file_names_do_not_trigger_a_checklist():
    # Review finding: "Please also update `README.md`." injected a fake checklist.
    assert extract_task_checklist("Thanks. Please also update `README.md`.") == []
    assert extract_task_checklist("Thanks. Please also rename `render_legend`.") == []
    assert task_checklist_note(_ISSUE + "Please also update `README.md`.") is None
