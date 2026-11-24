"""按业务组生成签发计划。

对账相符的组可逐组签发；受坏行或冲突牵连的组带原因暂缓；
坏行无法可靠归组时整批暂缓。
"""

# 暂缓原因码 -> 复核证据中的中文说明
HOLD_REASONS = {
    "UNATTRIBUTABLE_BAD_ROW": "存在无法可靠归组的坏行，整批暂缓",
    "CROSS_GROUP_CONFLICT": "同一记录键在多个业务组来源中冲突",
    "ISOLATED_BAD_ROW": "该组来源含已隔离坏行",
    "CASE_NOT_READY": "组内对账未通过或存在领域差异",
}

# 可签发状态
ELIGIBLE = "ELIGIBLE"
HELD = "HELD"
SIGNED = "SIGNED"


def _case_issues(intake):
    """汇总每个业务组被暂缓的原因。"""
    blocked = {}

    def add(case, reason):
        blocked.setdefault(case, [])
        if reason not in blocked[case]:
            blocked[case].append(reason)

    if intake.get("ungroupable"):
        batch_hold = "UNATTRIBUTABLE_BAD_ROW"
        # 整批暂缓：所有组都要挂原因，未挂具体原因的组在计划阶段补齐
    else:
        batch_hold = None
    for row in intake.get("isolation", ()):
        # 回放重复（DUPLICATE_REPLAY）的采信行仍在组内，不阻断签发；
        # 只有真正的坏行才隔离对应组。
        if row["reason"] != "DUPLICATE_REPLAY":
            add(row["case"], "ISOLATED_BAD_ROW")
    cross_groups = set()
    for row in intake.get("cross_conflicts", ()):
        add(row["case"], "CROSS_GROUP_CONFLICT")
        cross_groups.add(row["case"])
    return blocked, cross_groups, batch_hold


def build_release_plan(intake, cases, decisions=None):
    """根据输入、对账结果和已存复核结论构建逐组签发计划。

    decisions: {case: {"status": ..., "note": ..., "reviewed": ...}}
    """
    blocked, cross_groups, batch_hold = _case_issues(intake)
    decisions = decisions or {}
    plan_cases = []
    signed = held = eligible = 0
    for case in cases:
        name = case["case"]
        reasons = list(blocked.get(name, ()))
        if case["status"] != "READY":
            if "CASE_NOT_READY" not in reasons:
                reasons.append("CASE_NOT_READY")
        if batch_hold and batch_hold not in reasons:
            reasons.append(batch_hold)
        review = decisions.get(name)
        is_signed = bool(review and review["status"] == "APPROVED")
        releasable = not reasons and not is_signed
        if is_signed:
            state = SIGNED
            signed += 1
        elif releasable:
            state = ELIGIBLE
            eligible += 1
        else:
            state = HELD
            held += 1
        item = {
            "case": name,
            "state": state,
            "releasable": releasable,
            "hold_reasons": reasons,
            "hold_text": [HOLD_REASONS[r] for r in reasons],
        }
        if review:
            item["review"] = {
                "status": review["status"],
                "note": review["note"],
                "reviewed": review["reviewed"],
                "revision": review.get("revision", 0),
            }
        plan_cases.append(item)
    ungroupable = intake.get("ungroupable", ())
    return {
        "cases": plan_cases,
        "eligible": eligible,
        "signed": signed,
        "held": held,
        "batch_hold": batch_hold,
        "ungroupable": ungroupable,
        "cross_conflict_cases": sorted(cross_groups),
        "all_signed": bool(plan_cases)
        and signed == len(plan_cases),
        "any_signed": signed > 0,
    }
