import json
from hashlib import sha256

from app.evidence.render import artifact
from app.review.service import execute, load, review


def decide(case, status="APPROVED", note="逐组复核证据"):
    return {"decisions": [{"case": case, "revision": 0, "status": status, "note": note}]}


def test_origin_checksum_matches_input(store, clean):
    output = json.loads(artifact(execute(store, clean)))
    assert output["manifest"]["sha256"] == sha256(clean).hexdigest()


def test_same_revision_bytes_are_deterministic(store, clean):
    run = execute(store, clean)
    assert artifact(run) == artifact(store.load(run["id"]))


def test_export_preserves_isolated_row_numbers(store, dirty):
    output = json.loads(artifact(execute(store, dirty)))
    isolated = output["intake"]["isolation"]
    assert len(isolated) == 5 and all(row["line"] > 1 for row in isolated)


def test_export_states_which_groups_are_signed_held_and_why(store, dirty):
    run = execute(store, dirty)
    review(store, run["id"], decide("0001", note="0001 已复核签发"))
    review(store, run["id"], {"decisions": [{"case": "0003", "revision": 0, "status": "HELD", "note": "变更冲突暂缓"}]})
    output = json.loads(artifact(load(store, run["id"])))
    assert output["schema"] == "review-evidence/2"
    groups = {g["case"]: g for g in output["groups"]}
    assert groups["0001"]["state"] == "SIGNED"
    assert groups["0001"]["review"]["note"] == "0001 已复核签发"
    assert groups["0002"]["state"] == "ELIGIBLE"
    assert groups["0003"]["state"] == "HELD"
    assert groups["0003"]["hold_reasons"] == ["CASE_NOT_READY"]
    assert groups["0003"]["review"]["status"] == "HELD"
    assert groups["0004"]["hold_text"] == ["组内对账未通过或存在领域差异"]
    # 逐组复核结论同样进入证据
    assert output["case_reviews"]["0001"]["status"] == "APPROVED"


def test_export_marks_ungroupable_batch_hold(store):
    from conftest import csv_data

    data = csv_data(
        [
            ["R1", "A", "opening", "0", "100", "0", "n"],
            ["R2", "A", "close", "100", "100", "0", "n"],
        ]
    ) + b"BADROW\n"
    run = execute(store, data)
    output = json.loads(artifact(load(store, run["id"])))
    assert output["release"]["batch_hold"] == "UNATTRIBUTABLE_BAD_ROW"
    assert output["intake"]["ungroupable"][0]["line"] == 4
    assert output["groups"][0]["hold_reasons"] == ["UNATTRIBUTABLE_BAD_ROW"]


def test_evidence_404(client):
    assert client.get("/api/runs/unknown/evidence").status_code == 404


def test_download_attachment(client):
    run = client.post("/api/runs", data={"sample": "clean"}).json
    response = client.get("/api/runs/" + run["id"] + "/evidence")
    assert (
        response.status_code == 200
        and "attachment" in response.headers["Content-Disposition"]
    )
    assert response.json["schema"] == "review-evidence/2"
