import io

import pytest


@pytest.mark.parametrize(
    "stage", ["intake", "prepare", "calculate", "policy", "balance"]
)
def test_stage_has_http_entry_and_no_database_write(client, stage):
    response = client.post("/api/stages/" + stage, data={"sample": "dirty"})
    assert response.status_code == 200 and response.json["intake"]["rejected"] == 5
    assert client.get("/api/runs").json == {"items": []}


def test_upload_uses_input_content(client, clean):
    a = client.post("/api/runs", data={"file": (io.BytesIO(clean), "input.csv")})
    b = client.post("/api/runs", data={"sample": "clean"})
    assert a.status_code == 200 and a.json["id"] == b.json["id"]


def test_unknown_stage_and_sample(client):
    assert (
        client.post("/api/stages/unknown", data={"sample": "clean"}).status_code == 404
    )
    assert client.post("/api/runs", data={"sample": "unknown"}).status_code == 404


def test_bad_upload_leaves_history_empty(client):
    result = client.post(
        "/api/runs", data={"file": (io.BytesIO(b"wrong,header\n"), "bad.csv")}
    )
    assert result.status_code == 422 and result.json["code"] == "HEADER_MISMATCH"
    assert client.get("/api/runs").json["items"] == []


def test_patch_signs_single_group_and_returns_release_plan(client):
    run = client.post("/api/runs", data={"sample": "dirty"}).json
    response = client.patch(
        f"/api/runs/{run['id']}",
        json={
            "decisions": [
                {"case": "0001", "revision": 0, "status": "APPROVED", "note": "0001 复核通过"}
            ]
        },
    )
    assert response.status_code == 200
    groups = {g["case"]: g for g in response.json["report"]["balance"]["release"]["cases"]}
    assert groups["0001"]["state"] == "SIGNED"
    assert groups["0002"]["state"] == "ELIGIBLE"


def test_patch_rejects_ineligible_group_with_409(client):
    run = client.post("/api/runs", data={"sample": "dirty"}).json
    response = client.patch(
        f"/api/runs/{run['id']}",
        json={
            "decisions": [
                {"case": "0003", "revision": 0, "status": "APPROVED", "note": "冲突组试图签发"}
            ]
        },
    )
    assert response.status_code == 409 and response.json["code"] == "CASE_NOT_ELIGIBLE"


def test_patch_signed_group_conflict_409_and_preserves_evidence(client):
    run = client.post("/api/runs", data={"sample": "clean"}).json
    client.patch(
        f"/api/runs/{run['id']}",
        json={
            "decisions": [
                {"case": "0001", "revision": 0, "status": "APPROVED", "note": "0001 已签发"}
            ]
        },
    )
    response = client.patch(
        f"/api/runs/{run['id']}",
        json={
            "decisions": [
                {"case": "0001", "revision": 1, "status": "HELD", "note": "试图覆盖已签组"}
            ]
        },
    )
    assert response.status_code == 409 and response.json["code"] == "CASE_FINALIZED"
    loaded = client.get(f"/api/runs/{run['id']}").json
    assert loaded["case_reviews"]["0001"]["status"] == "APPROVED"
    assert loaded["case_reviews"]["0001"]["note"] == "0001 已签发"


def test_patch_stale_revision_returns_409(client):
    run = client.post("/api/runs", data={"sample": "clean"}).json
    client.patch(
        f"/api/runs/{run['id']}",
        json={
            "decisions": [
                {"case": "0001", "revision": 0, "status": "HELD", "note": "先暂缓 0001"}
            ]
        },
    )
    response = client.patch(
        f"/api/runs/{run['id']}",
        json={
            "decisions": [
                {"case": "0001", "revision": 0, "status": "HELD", "note": "旧版本重试"}
            ]
        },
    )
    assert response.status_code == 409 and response.json["code"] == "STALE_REVIEW"


def test_patch_unknown_case_returns_422(client):
    run = client.post("/api/runs", data={"sample": "clean"}).json
    response = client.patch(
        f"/api/runs/{run['id']}",
        json={
            "decisions": [
                {"case": "9999", "revision": 0, "status": "APPROVED", "note": "不存在的组"}
            ]
        },
    )
    assert response.status_code == 422 and response.json["code"] == "CASE_UNKNOWN"
