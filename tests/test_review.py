import pytest

from app.business import DomainIssue
from app.review.service import execute, load, review


def decide(case, revision=0, status="APPROVED", note="来源已逐组复核"):
    return {"decisions": [{"case": case, "revision": revision, "status": status, "note": note}]}


def test_byte_identical_rerun_keeps_run_and_manifest(store, clean):
    first = execute(store, clean)
    second = execute(store, clean)
    assert first["id"] == second["id"] and len(store.list()) == 1


def test_different_source_starts_new_run(store, clean, dirty):
    assert execute(store, clean)["id"] != execute(store, dirty)["id"]
    assert len(store.list()) == 2


def test_valid_group_approval_trims_note(store, clean):
    run = execute(store, clean)
    output = review(
        store,
        run["id"],
        decide("0001", note="  0001 源文件已复核  "),
    )
    group = output["case_reviews"]["0001"]
    assert (group["status"], group["note"], group["revision"]) == (
        "APPROVED",
        "0001 源文件已复核",
        1,
    )
    assert output["report"]["balance"]["release"]["signed"] == 1


def test_review_optimistic_lock(store, clean):  # TRAP-26
    run = execute(store, clean)
    review(store, run["id"], decide("0001", status="HELD", note="请核对 0001"))
    with pytest.raises(DomainIssue, match="STALE_REVIEW"):
        review(store, run["id"], decide("0001", status="HELD", note="旧版本复核"))
    # 正确版本号仍可继续提交
    review(store, run["id"], decide("0001", revision=1, note="新版本复核意见"))


def test_ineligible_group_cannot_be_approved(store, dirty):
    run = execute(store, dirty)
    with pytest.raises(DomainIssue, match="CASE_NOT_ELIGIBLE"):
        review(store, run["id"], decide("0003", note="试图签发冲突组"))
    # 整批未写入任何结论
    assert store.load(run["id"])["case_reviews"] == {}


def test_ready_groups_sign_independently_while_others_hold(store, dirty):
    run = execute(store, dirty)
    output = review(store, run["id"], decide("0001", note="0001 对账相符"))
    states = {g["case"]: g["state"] for g in output["report"]["balance"]["release"]["cases"]}
    assert states == {
        "0001": "SIGNED",
        "0002": "ELIGIBLE",
        "0003": "HELD",
        "0004": "HELD",
    }
    review(store, run["id"], decide("0002", note="0002 对账相符"))
    review(store, run["id"], decide("0004", status="HELD", note="0004 差异待查"))
    final = load(store, run["id"])
    assert final["status"] == "HELD"  # 还有未签的组
    assert final["report"]["balance"]["release"]["signed"] == 2


def test_signed_group_is_final_and_cannot_be_overwritten(store, clean):
    run = execute(store, clean)
    review(store, run["id"], decide("0001", note="0001 完成最终复核"))
    with pytest.raises(DomainIssue, match="CASE_FINALIZED"):
        review(store, run["id"], decide("0001", revision=1, status="HELD", note="试图撤销签发"))
    # 已签金额与证据保留
    assert store.load(run["id"])["case_reviews"]["0001"]["status"] == "APPROVED"


def test_batch_approved_only_when_all_groups_signed(store, clean):
    run = execute(store, clean)
    review(store, run["id"], decide("0001", note="先签 0001"))
    assert load(store, run["id"])["status"] == "HELD"
    review(store, run["id"], decide("0002", note="再签 0002"))
    assert load(store, run["id"])["status"] == "APPROVED"


def test_unknown_case_and_malformed_payload_rejected(store, clean):
    run = execute(store, clean)
    with pytest.raises(DomainIssue, match="CASE_UNKNOWN"):
        review(store, run["id"], decide("9999", note="不存在的业务组"))
    with pytest.raises(DomainIssue, match="REVIEW_FIELDS"):
        review(store, run["id"], {"decisions": []})
    with pytest.raises(DomainIssue, match="REVIEW_FIELDS"):
        review(store, run["id"], decide("0001", note="短"))


def test_batch_decision_is_atomic(store, dirty):
    run = execute(store, dirty)
    payload = {
        "decisions": [
            {"case": "0001", "revision": 0, "status": "APPROVED", "note": "合格组"},
            {"case": "0003", "revision": 0, "status": "APPROVED", "note": "不合格组"},
        ]
    }
    with pytest.raises(DomainIssue, match="CASE_NOT_ELIGIBLE"):
        review(store, run["id"], payload)
    assert store.load(run["id"])["case_reviews"] == {}
