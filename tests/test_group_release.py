import pytest

from app.business import DomainIssue
from app.intake.service import inspect
from app.modules.pipeline import run
from app.review.service import execute, review
from conftest import csv_data


def opening(record, case, amount="100"):
    return [record, case, "opening", "0", amount, "0", "来源行"]


def close(record, case, amount="100"):
    return [record, case, "close", "100", amount, "0", "来源行"]


def test_same_record_key_conflicting_across_groups_holds_both_groups():
    data = csv_data(
        [
            opening("R1", "A"),
            close("R2", "A"),
            ["R1", "B", "opening", "0", "200", "0", "冲突来源"],
            close("R3", "B", "200"),
            opening("R4", "C", "50"),
            close("R5", "C", "50"),
        ]
    )
    intake = inspect(data)
    assert {row["record"] for row in intake["cross_conflicts"]} == {"R1"}
    plan = run(data)["balance"]["release"]
    by_case = {item["case"]: item for item in plan["cases"]}
    assert by_case["A"]["hold_reasons"] == ["CROSS_GROUP_CONFLICT"]
    assert by_case["B"]["hold_reasons"] == ["CROSS_GROUP_CONFLICT"]
    assert by_case["C"]["state"] == "ELIGIBLE"
    assert plan["cross_conflict_cases"] == ["A", "B"]


def test_identical_cross_group_key_also_holds_both_groups():
    data = csv_data(
        [
            opening("R1", "A"),
            close("R2", "A"),
            opening("R1", "B"),  # 同键同内容，但跨组出现，仍需核对
            close("R3", "B"),
        ]
    )
    intake = inspect(data)
    assert {row["record"] for row in intake["cross_conflicts"]} == {"R1"}
    plan = run(data)["balance"]["release"]
    assert all("CROSS_GROUP_CONFLICT" in item["hold_reasons"] for item in plan["cases"])


def test_same_group_replay_does_not_block_any_group():
    data = csv_data(
        [
            opening("R1", "A"),
            close("R2", "A"),
            close("R2", "A"),  # 组内完全重复，回放去重
        ]
    )
    intake = inspect(data)
    assert intake["cross_conflicts"] == []
    assert intake["reasons"].get("DUPLICATE_REPLAY") == 1
    plan = run(data)["balance"]["release"]
    assert plan["cases"][0]["state"] == "ELIGIBLE"
    assert plan["cases"][0]["hold_reasons"] == []


def test_ungroupable_bad_row_holds_the_whole_batch(store):
    data = csv_data(
        [
            opening("R1", "A"),
            close("R2", "A"),
        ]
    ) + b"LOST_ROW\n"  # 无法定位业务组的坏行
    intake = inspect(data)
    assert len(intake["ungroupable"]) == 1
    assert intake["ungroupable"][0]["reason"] == "COLUMN_COUNT"
    report = run(data)
    plan = report["balance"]["release"]
    assert plan["batch_hold"] == "UNATTRIBUTABLE_BAD_ROW"
    assert all(item["state"] == "HELD" for item in plan["cases"])
    run_record = execute(store, data)
    with pytest.raises(DomainIssue, match="CASE_NOT_ELIGIBLE"):
        review(
            store,
            run_record["id"],
            {"decisions": [{"case": "A", "revision": 0, "status": "APPROVED", "note": "整批应被暂缓"}]},
        )


def test_attributable_bad_row_only_blocks_its_own_group():
    # case 列合法，可可靠归组到 B；坏行进隔离，A 不受影响仍可签
    data = csv_data(
        [
            opening("R1", "A"),
            close("R2", "A"),
            ["R9", "B", "opening", "-", "0", "0", "缺测坏行"],
        ]
    )
    intake = inspect(data)
    assert intake["isolation"][0]["case"] == "B"
    assert intake["isolation"][0]["reason"] == "MISSING_NUMBER"
    plan = run(data)["balance"]["release"]
    by_case = {item["case"]: item for item in plan["cases"]}
    assert list(by_case) == ["A"]  # B 的行全部被隔离，没有可评估组
    assert by_case["A"]["state"] == "ELIGIBLE"
    assert by_case["A"]["hold_reasons"] == []
