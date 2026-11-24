from collections import Counter

from app.modules.release import build_release_plan


def balance(intake, cases, decisions=None):
    ungroupable = intake.get("ungroupable", ())
    accounted = (
        intake["accepted"]
        + intake["rejected"]
        + len(ungroupable)
        + intake["blank"]
        + intake["repeated"]
    )
    observed = sum(len(case["records"]) for case in cases)
    status = Counter(case["status"] for case in cases)
    ready = status.pop("READY", 0)
    plan = build_release_plan(intake, cases, decisions)
    return dict(
        input=intake["input"],
        accepted=intake["accepted"],
        isolated=intake["rejected"] + len(ungroupable),
        ignored=intake["blank"] + intake["repeated"],
        accounted=accounted,
        balanced=accounted == intake["input"] and observed == intake["accepted"],
        ready=ready,
        pending=len(cases) - ready,
        issues=dict(sorted(status.items())),
        # 仍有可逐组签发的业务组
        releasable=plan["eligible"] > 0,
        release=plan,
    )
