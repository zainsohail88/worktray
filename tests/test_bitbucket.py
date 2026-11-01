from worktray.sources.bitbucket import bitbucket_reasons, failing_status

ME = "{me}"


def pr(*, approved_by_other: bool = False, changes_requested: bool = False) -> dict:
    participants = [{"user": {"uuid": "{other}"}, "approved": approved_by_other, "state": "changes_requested" if changes_requested else None}]
    return {"author": {"uuid": ME}, "participants": participants, "reviewers": []}


def test_approved_pr_with_green_builds_is_ready_to_merge():
    reasons = bitbucket_reasons(pr(approved_by_other=True), ME, [{"state": "SUCCESSFUL"}], [])

    assert reasons == ["Ready to merge"]


def test_approved_pr_without_builds_is_not_ready():
    assert bitbucket_reasons(pr(approved_by_other=True), ME, [], []) == []


def test_changes_requested_blocks_ready_to_merge():
    reasons = bitbucket_reasons(pr(approved_by_other=True, changes_requested=True), ME, [{"state": "SUCCESSFUL"}], [])

    assert reasons == ["Changes requested"]


def test_failing_status_names_the_build_and_links_it():
    statuses = [{"state": "SUCCESSFUL"}, {"state": "FAILED", "name": "Unit tests", "url": "https://ci.example/9"}]

    assert failing_status(statuses) == ("https://ci.example/9", "Unit tests")


def test_green_builds_have_no_failing_status():
    assert failing_status([{"state": "SUCCESSFUL"}]) == ("", "")
