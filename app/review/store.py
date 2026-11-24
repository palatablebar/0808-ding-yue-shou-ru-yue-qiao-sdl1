import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from app.business import DomainIssue

SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, report TEXT NOT NULL, created TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING', revision INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '', reviewed TEXT
);
CREATE TABLE IF NOT EXISTS case_reviews (
    run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT NOT NULL,
    reviewed TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, case_id)
);
CREATE INDEX IF NOT EXISTS case_reviews_run ON case_reviews(run_id);
"""


class Store:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=15)) as db, db:
            db.row_factory = sqlite3.Row
            db.executescript(SCHEMA)
            yield db

    def register(self, run_id, report):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(id,report,created) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING",
                (
                    run_id,
                    json.dumps(report, ensure_ascii=False),
                    report["manifest"]["created"],
                ),
            )
        return self.load(run_id)

    def load(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise DomainIssue("RUN_NOT_FOUND")
            result = dict(row)
            result["report"] = json.loads(result["report"])
            result["case_reviews"] = {
                r["case_id"]: dict(r)
                for r in db.execute(
                    "SELECT case_id,status,note,reviewed,revision "
                    "FROM case_reviews WHERE run_id=? ORDER BY case_id",
                    (run_id,),
                )
            }
        return result

    def list(self):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,created,status,revision,note FROM runs ORDER BY created DESC,id LIMIT 50"
                )
            ]

    def review_cases(self, run_id, decisions, now):
        """原子地提交一组逐组复核结论。

        已签发组不可覆盖；并发下靠数据库约束与条件更新保证只有一方胜出。
        所有校验与写入都在同一个写事务内完成，避免先查后写的竞态。
        """
        with self.connect() as db:
            if db.execute(
                "SELECT 1 FROM runs WHERE id=?", (run_id,)
            ).fetchone() is None:
                raise DomainIssue("RUN_NOT_FOUND")
            for case_id, payload in decisions:
                row = db.execute(
                    "SELECT status,revision FROM case_reviews WHERE run_id=? AND case_id=?",
                    (run_id, case_id),
                ).fetchone()
                if row is not None and row["status"] == "APPROVED":
                    # 已签组的金额和证据不能被覆盖
                    raise DomainIssue("CASE_FINALIZED")
                expected = payload["revision"]
                if row is None:
                    if expected != 0:
                        raise DomainIssue("STALE_REVIEW")
                    try:
                        db.execute(
                            "INSERT INTO case_reviews"
                            "(run_id,case_id,status,note,reviewed,revision) "
                            "VALUES (?,?,?,?,?,1)",
                            (
                                run_id,
                                case_id,
                                payload["status"],
                                payload["note"],
                                now,
                            ),
                        )
                    except sqlite3.IntegrityError:
                        # 并发事务抢先插入同一组：版本已过期
                        raise DomainIssue("STALE_REVIEW")
                else:
                    if expected != row["revision"]:
                        raise DomainIssue("STALE_REVIEW")
                    cursor = db.execute(
                        "UPDATE case_reviews SET status=?,note=?,reviewed=?,"
                        "revision=revision+1 WHERE run_id=? AND case_id=? AND revision=?",
                        (
                            payload["status"],
                            payload["note"],
                            now,
                            run_id,
                            case_id,
                            expected,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise DomainIssue("STALE_REVIEW")
            db.execute(
                "UPDATE runs SET revision=revision+1,reviewed=? WHERE id=?",
                (now, run_id),
            )
        return self.load(run_id)
