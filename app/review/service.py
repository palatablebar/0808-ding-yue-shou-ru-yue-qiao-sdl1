from datetime import datetime, timezone
from hashlib import sha256
from time import monotonic

from app.business import DomainIssue
from app.config import RULE_VERSION
from app.modules.pipeline import run
from app.modules.release import build_release_plan


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def execute(store, data):
    start = monotonic()
    fingerprint = sha256(data).hexdigest()
    run_id = sha256(f"{RULE_VERSION}:{fingerprint}".encode()).hexdigest()
    try:
        return store.load(run_id)
    except DomainIssue as error:
        if error.code != "RUN_NOT_FOUND":
            raise
    report = run(data)
    report["manifest"] = dict(
        sha256=fingerprint,
        version=RULE_VERSION,
        created=now(),
        duration_ms=round((monotonic() - start) * 1000, 3),
        bytes=len(data),
        run_id=run_id,
    )
    return store.register(run_id, report)


def _review_decisions(case_reviews):
    return {
        case_id: {
            "status": item["status"],
            "note": item["note"],
            "reviewed": item["reviewed"],
            "revision": item.get("revision", 0),
        }
        for case_id, item in case_reviews.items()
    }


def aggregate(report, case_reviews):
    """根据逐组复核结论推导批次级状态，并刷新签发计划。"""
    decisions = _review_decisions(case_reviews)
    plan = build_release_plan(report["intake"], report["cases"], decisions)
    report["balance"]["release"] = plan
    signed = plan["signed"]
    total = len(plan["cases"])
    if total and signed == total:
        status = "APPROVED"
    elif case_reviews:
        status = "HELD"
    else:
        status = "PENDING"
    note = "；".join(
        f"{case_id}:{item['note']}"
        for case_id, item in sorted(case_reviews.items())
    )[:200]
    return status, note, plan


def load(store, run_id):
    """读取批次并按当前逐组结论重算汇总状态与签发计划。"""
    record = store.load(run_id)
    status, note, _ = aggregate(record["report"], record["case_reviews"])
    record["status"] = status
    record["note"] = note
    return record


def _validate_entry(entry, known_cases):
    if not isinstance(entry, dict):
        raise DomainIssue("REVIEW_FIELDS")
    case_id = entry.get("case")
    if not isinstance(case_id, str) or case_id not in known_cases:
        raise DomainIssue("CASE_UNKNOWN")
    revision = entry.get("revision")
    case_status = entry.get("status")
    case_note = entry.get("note")
    if (
        type(revision) is not int
        or revision < 0
        or case_status not in ("APPROVED", "HELD")
        or not isinstance(case_note, str)
        or not (3 <= len(case_note.strip()) <= 200)
    ):
        raise DomainIssue("REVIEW_FIELDS")
    return case_id, {
        "revision": revision,
        "status": case_status,
        "note": case_note.strip(),
    }


def review(store, run_id, values):
    if not isinstance(values, dict) or not isinstance(values.get("decisions"), list):
        raise DomainIssue("REVIEW_FIELDS")
    if not values["decisions"]:
        raise DomainIssue("REVIEW_FIELDS")
    current = store.load(run_id)
    known = {case["case"] for case in current["report"]["cases"]}
    parsed, seen = [], set()
    for entry in values["decisions"]:
        case_id, payload = _validate_entry(entry, known)
        if case_id in seen:
            raise DomainIssue("REVIEW_FIELDS")
        seen.add(case_id)
        parsed.append((case_id, payload))

    plan = build_release_plan(
        current["report"]["intake"],
        current["report"]["cases"],
        _review_decisions(current["case_reviews"]),
    )
    plan_by_case = {item["case"]: item for item in plan["cases"]}
    for case_id, payload in parsed:
        if payload["status"] == "APPROVED":
            item = plan_by_case[case_id]
            if item["state"] == "SIGNED":
                raise DomainIssue("CASE_FINALIZED")
            if not item["releasable"]:
                raise DomainIssue("CASE_NOT_ELIGIBLE")
    # 写事务内会再次原子校验已签组与版本号，覆盖并发竞态。
    updated = store.review_cases(run_id, parsed, now())
    status, note, _ = aggregate(updated["report"], updated["case_reviews"])
    updated["status"] = status
    updated["note"] = note
    return updated
