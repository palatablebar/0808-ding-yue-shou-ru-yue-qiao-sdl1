from app.modules.pipeline import run
from app.modules.reconcile import balance


def test_input_row_conservation(dirty):
    checks = run(dirty)["balance"]
    assert (
        checks["input"] == checks["accepted"] + checks["isolated"] + checks["ignored"]
    )


def test_business_cases_conserve_input(dirty):
    report = run(dirty)
    assert len(report["cases"]) == 4
    assert (
        sum(len(c["records"]) for c in report["cases"]) == report["balance"]["accepted"]
    )


def test_clean_case_set_is_releasable(clean):
    plan = run(clean)["balance"]["release"]
    assert plan["eligible"] == 2 and plan["signed"] == 0 and plan["held"] == 0
    assert all(item["state"] == "ELIGIBLE" for item in plan["cases"])


def test_dirty_batch_releases_ready_groups_only(dirty):
    checks = run(dirty)["balance"]
    plan = checks["release"]
    assert checks["isolated"] == 5 and checks["pending"] == 2
    # 仍有可逐组签发的组，但整批不能整体放行
    assert checks["releasable"] is True
    assert plan["eligible"] == 2 and plan["held"] == 2
    by_case = {item["case"]: item for item in plan["cases"]}
    assert by_case["0001"]["state"] == "ELIGIBLE"
    assert by_case["0002"]["state"] == "ELIGIBLE"
    assert by_case["0003"]["hold_reasons"] == ["CASE_NOT_READY"]
    assert by_case["0004"]["hold_reasons"] == ["CASE_NOT_READY"]


def test_empty_case_set_cannot_release():
    checks = balance(dict(input=1, accepted=0, rejected=0, blank=1, repeated=0), [])
    assert checks["balanced"] and not checks["releasable"]
    assert checks["release"]["eligible"] == 0


def test_miscounted_lines_cannot_release():
    checks = balance(
        dict(input=9, accepted=1, rejected=0, blank=0, repeated=0),
        [dict(case="A", records=["a"], status="READY")],
    )
    assert not checks["balanced"]


def test_replay_duplicate_does_not_block_group():
    # incoming.csv 第 21 行是 0001 组的回放重复，0001 仍应可签
    import pathlib

    data = (
        pathlib.Path(__file__).resolve().parents[1]
        / "sample_data"
        / "incoming.csv"
    ).read_bytes()
    by_case = {item["case"]: item for item in run(data)["balance"]["release"]["cases"]}
    assert by_case["0001"]["state"] == "ELIGIBLE"
    assert "ISOLATED_BAD_ROW" not in by_case["0001"]["hold_reasons"]
