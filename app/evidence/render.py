import json


def artifact(run):
    release = run["report"]["balance"]["release"]
    packet = {
        "schema": "review-evidence/2",
        "manifest": run["report"]["manifest"],
        "balance": run["report"]["balance"],
        "release": release,
        "groups": [
            {
                "case": item["case"],
                "state": item["state"],
                "releasable": item["releasable"],
                "hold_reasons": item["hold_reasons"],
                "hold_text": item["hold_text"],
                "review": item.get("review"),
            }
            for item in release["cases"]
        ],
        "cases": run["report"]["cases"],
        "intake": run["report"]["intake"],
        "review": {
            key: run.get(key, "")
            for key in ("status", "revision", "note", "reviewed")
        },
        "case_reviews": run["case_reviews"],
    }
    return (
        json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
