from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app.business import DomainIssue
from app.review.service import execute, review


def test_parallel_rerun_commits_single_row(store, clean):
    start = Barrier(4)

    def load():
        start.wait(3)
        return execute(store, clean)

    with ThreadPoolExecutor(max_workers=4) as threads:
        results = list(threads.map(lambda _: load(), range(4)))
    assert all(result["id"] == results[0]["id"] for result in results)
    assert len(store.list()) == 1


def test_parallel_reviews_on_different_groups_both_commit(store, clean):
    run = execute(store, clean)
    start = Barrier(2)

    def attempt(case, note):
        start.wait(3)
        try:
            review(
                store,
                run["id"],
                {"decisions": [{"case": case, "revision": 0, "status": "APPROVED", "note": note}]},
            )
            return case, "OK"
        except DomainIssue as error:
            return case, error.code

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = dict(
            threads.map(lambda item: attempt(*item), [("0001", "甲复核 0001"), ("0002", "乙复核 0002")])
        )
    assert results == {"0001": "OK", "0002": "OK"}
    reviews = store.load(run["id"])["case_reviews"]
    assert {case: item["status"] for case, item in reviews.items()} == {
        "0001": "APPROVED",
        "0002": "APPROVED",
    }


def test_parallel_contest_on_same_group_has_one_winner(store, clean):
    run = execute(store, clean)
    start = Barrier(2)

    def attempt(note):
        start.wait(3)
        try:
            review(
                store,
                run["id"],
                {"decisions": [{"case": "0001", "revision": 0, "status": "HELD", "note": note}]},
            )
            return "OK"
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(attempt, ["来源待检查", "分组待处理"]))
    assert sorted(results) == ["OK", "STALE_REVIEW"]
    assert store.load(run["id"])["case_reviews"]["0001"]["revision"] == 1


def test_signed_group_survives_concurrent_overwrite(store, clean):
    run = execute(store, clean)
    review(
        store,
        run["id"],
        {"decisions": [{"case": "0001", "revision": 0, "status": "APPROVED", "note": "已签发金额"}]},
    )
    start = Barrier(2)

    def attempt(note):
        start.wait(3)
        try:
            review(
                store,
                run["id"],
                {"decisions": [{"case": "0001", "revision": 1, "status": "HELD", "note": note}]},
            )
            return "OK"
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(attempt, ["并发覆盖甲", "并发覆盖乙"]))
    assert results == ["CASE_FINALIZED", "CASE_FINALIZED"]
    assert store.load(run["id"])["case_reviews"]["0001"]["status"] == "APPROVED"


def test_concurrent_approvals_of_same_group_have_one_winner(store, clean):
    run = execute(store, clean)
    start = Barrier(4)

    def attempt(i):
        start.wait(5)
        try:
            review(
                store,
                run["id"],
                {"decisions": [{"case": "0002", "revision": 0, "status": "APPROVED", "note": f"并发签发编号{i}"}]},
            )
            return "OK"
        except DomainIssue as error:
            return error.code

    with ThreadPoolExecutor(max_workers=4) as threads:
        results = list(threads.map(attempt, range(4)))
    assert results.count("OK") == 1
    # 败者要么版本过期，要么发现该组已被抢先签发，均不得再写入
    assert all(code in {"STALE_REVIEW", "CASE_FINALIZED"} for code in results if code != "OK")
    review_row = store.load(run["id"])["case_reviews"]["0002"]
    assert review_row["status"] == "APPROVED" and review_row["revision"] == 1
