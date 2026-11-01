from worktray.sources.github import failing_check, github_reasons


def pr(decision: str = "REVIEW_REQUIRED", rollup: str | None = None, contexts: list[dict] | None = None) -> dict:
    return {
        "author": {"login": "me"},
        "reviewDecision": decision,
        "reviewThreads": {"nodes": []},
        "statusCheckRollup": {"state": rollup, "contexts": {"nodes": contexts or []}} if rollup else None,
    }


def test_approved_pr_with_green_checks_is_ready_to_merge():
    assert github_reasons(pr("APPROVED", "SUCCESS"), own=True, requested=False) == ["Ready to merge"]


def test_approved_pr_with_pending_checks_is_not_ready():
    assert github_reasons(pr("APPROVED", "PENDING"), own=True, requested=False) == []


def test_review_pending_pr_has_no_reason():
    assert github_reasons(pr(), own=True, requested=False) == []


def test_failing_check_run_names_the_run_and_links_it():
    contexts = [
        {"__typename": "StatusContext", "context": "build", "state": "SUCCESS", "targetUrl": "https://ci.example/1"},
        {"__typename": "CheckRun", "name": "approve", "conclusion": "FAILURE", "detailsUrl": "https://github.com/run/2"},
    ]

    assert failing_check(pr(rollup="FAILURE", contexts=contexts)) == ("https://github.com/run/2", "approve")


def test_failing_status_context_uses_its_target_url():
    contexts = [{"__typename": "StatusContext", "context": "Pull Request", "state": "FAILURE", "targetUrl": "https://ci.example/3"}]

    assert failing_check(pr(rollup="FAILURE", contexts=contexts)) == ("https://ci.example/3", "Pull Request")


def test_failing_check_drops_a_link_that_is_not_https():
    contexts = [{"__typename": "StatusContext", "context": "legacy", "state": "ERROR", "targetUrl": "javascript:alert(1)"}]

    assert failing_check(pr(rollup="ERROR", contexts=contexts)) == ("", "legacy")
