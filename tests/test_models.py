import pytest

from worktray.models import WAITING_ON_REVIEW, Item, https_only, idle_reasons, review_lane


def test_pr_with_no_reason_has_no_lane():
    assert review_lane([]) == ""


def test_pr_waiting_on_its_reviewer_waits():
    assert review_lane([WAITING_ON_REVIEW]) == "waiting"


@pytest.mark.parametrize("reasons", [["Review requested"], ["Failing checks", "Ready to merge"]])
def test_pr_with_any_other_reason_needs_me(reasons):
    assert review_lane(reasons) == "needs_me"


def test_idle_pr_waits_on_its_reviewer():
    assert idle_reasons(draft=False) == [WAITING_ON_REVIEW]


def test_idle_draft_pr_is_the_authors_move():
    assert review_lane(idle_reasons(draft=True)) == "needs_me"


def test_item_rejects_a_script_checks_link():
    with pytest.raises(ValueError):
        Item(key="k", title="t", source="github", checks_url="javascript:alert(1)")


def test_https_only_keeps_https_links():
    assert https_only("https://ci.example/1") == "https://ci.example/1"
