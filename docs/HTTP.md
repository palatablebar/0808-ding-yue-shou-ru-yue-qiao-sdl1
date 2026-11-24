# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。`balance` 阶段在 `balance.release` 中返回逐组签发计划。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批、当前逐组复核结论与重算后的批次状态。

`PATCH /api/runs/<id>` 按业务组提交复核，请求体为：

```json
{
  "decisions": [
    {"case": "0001", "revision": 0, "status": "APPROVED", "note": "0001 复核通过"}
  ]
}
```

- 一次可提交一个或多个组，整组结论在同一事务内原子生效；任一组不合法则全部不写入。
- `status` 为 `APPROVED`（签发）或 `HELD`（暂缓），意见长度 3 至 200 字。
- 只有签发计划中 `state=ELIGIBLE` 的组可签发；带暂缓原因的组签发返回 409 `CASE_NOT_ELIGIBLE`。
- 已签发组（`SIGNED`）不可再修改，返回 409 `CASE_FINALIZED`，其金额与证据保留不变。
- 版本号基于单组 `revision`：并发提交同一组时只有一方成功，另一方收到 409 `STALE_REVIEW`，刷新后重试；不同组互不阻塞。
- 业务组不存在返回 422 `CASE_UNKNOWN`。

## 签发计划 `balance.release`

| 字段 | 含义 |
|---|---|
| `cases[].state` | `ELIGIBLE` 可签发、`SIGNED` 已签发、`HELD` 暂缓 |
| `cases[].releasable` | 当前是否允许签发该组 |
| `cases[].hold_reasons` / `hold_text` | 暂缓原因码与中文说明 |
| `eligible` / `signed` / `held` | 各组数量 |
| `batch_hold` | 整批暂缓原因（如 `UNATTRIBUTABLE_BAD_ROW`），否则为 `null` |
| `cross_conflict_cases` | 因同一记录键跨组冲突而暂缓的业务组 |
| `ungroupable` | 无法可靠归组的坏行清单 |

暂缓原因码：`UNATTRIBUTABLE_BAD_ROW`（坏行无法归组，整批暂缓）、`CROSS_GROUP_CONFLICT`（记录键跨组冲突）、`ISOLATED_BAD_ROW`（组内含隔离坏行）、`CASE_NOT_READY`（组内对账未通过）。

`GET /api/runs/<id>/evidence` 下载 `review-evidence/2` JSON，逐组列出已签/暂缓状态、暂缓原因与复核意见，并包含运行清单、行号隔离（含无法归组与跨组冲突行）和业务证据。
