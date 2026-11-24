from collections import defaultdict
from re import fullmatch

ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,35}"


def attributable(values):
    """坏行能否可靠归入某个业务组。

    组标识位于第二列；缺失或不符合标识规则时无法可靠归组。
    """
    if len(values) < 2:
        return False
    case = values[1].strip()
    return bool(fullmatch(ID_PATTERN, case))


def partition(candidates):
    by_key = defaultdict(list)
    for line, row in candidates:
        by_key[row["record"]].append((line, row))
    accepted, rejected, cross_conflicts = [], [], []
    for key, entries in by_key.items():
        first = entries[0][1]
        groups = {row["case"] for _, row in entries}
        if len(groups) > 1:
            # 同一记录键出现在多个业务组：无论内容是否一致，牵涉的组
            # 都需暂缓核对；来源行全部保留，由签发计划统一挂冲突原因。
            accepted.extend(row for _, row in entries)
            cross_conflicts.extend(
                {
                    "line": line,
                    "record": key,
                    "case": row["case"],
                    "reason": "CROSS_GROUP_CONFLICT",
                }
                for line, row in entries
            )
            continue
        if any(row != first for _, row in entries):
            rejected.extend(
                {
                    "line": line,
                    "record": key,
                    "case": row["case"],
                    "reason": "DUPLICATE_CONFLICT",
                }
                for line, row in entries
            )
            continue
        accepted.append(first)
        rejected.extend(
            {
                "line": line,
                "record": key,
                "case": row["case"],
                "reason": "DUPLICATE_REPLAY",
            }
            for line, row in entries[1:]
        )
    return accepted, rejected, cross_conflicts
