"""Runs an attempt inside the browser (Pyodide). Same comparison rules as the PC app:
Python answers are compared with runner.same, SQL results with the PC app's SQL rules."""
import contextlib
import io
import time

from runner import clean_tb, same, short


def run_python(code, setup="", checks=None, mode="run"):
    buf = io.StringIO()
    ns = {"__name__": "__main__"}
    res = {"ok": True, "stdout": "", "error": None, "checks": []}
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            if setup:
                exec(compile(setup, "<setup>", "exec"), ns)
            exec(compile(code, "<your code>", "exec"), ns)
        except BaseException:  # noqa: BLE001
            res["ok"] = False
            res["error"] = clean_tb()
        if res["ok"] and mode == "check":
            for c in checks or []:
                row = {"label": c.get("label") or c.get("call") or c.get("assert"), "passed": False}
                try:
                    if "call" in c:
                        got = eval(compile(c["call"], "<check>", "eval"), ns)
                        exp = eval(compile(c["expected"], "<check>", "eval"), ns)
                        row.update(got=short(got), expected=short(exp), passed=bool(same(got, exp)))
                    else:
                        row["passed"] = bool(eval(compile(c["assert"], "<check>", "eval"), ns))
                except BaseException:  # noqa: BLE001
                    row["error"] = clean_tb().strip().splitlines()[-1]
                res["checks"].append(row)
            res["ok"] = all(r["passed"] for r in res["checks"])
    out = buf.getvalue()
    res["stdout"] = out if len(out) <= 20000 else out[:20000] + "\n… (output truncated)"
    return res


def _conn(seed):
    import sqlite3  # loaded on demand: Pyodide ships it as a separate package
    conn = sqlite3.connect(":memory:")
    conn.executescript(seed)
    return conn


def _query(conn, sql, limit_s=5.0):
    deadline = time.time() + limit_s
    conn.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    return cols, cur.fetchall()


def _norm(row):
    return tuple(round(v, 2) if isinstance(v, float) else v for v in row)


def run_sql(seed, sql, solution=None, ordered=False):
    import sqlite3
    sql = sql.strip()
    if not sql:
        return {"ok": False, "error": "Write a query first."}
    try:
        cols, rows = _query(_conn(seed), sql)
    except sqlite3.Error as exc:
        msg = str(exc)
        if "interrupted" in msg:
            msg = "Query took longer than 5s and was stopped."
        return {"ok": False, "error": f"SQL error: {msg}"}
    res = {"ok": True, "columns": cols, "rows": [list(r) for r in rows[:200]], "rowcount": len(rows)}
    if solution is None:
        return res
    ecols, erows = _query(_conn(seed), solution)
    got, exp = [_norm(r) for r in rows], [_norm(r) for r in erows]
    checks = [
        {"label": f"{len(ecols)} column(s)", "passed": len(cols) == len(ecols),
         "got": str(len(cols)), "expected": str(len(ecols))},
        {"label": f"{len(exp)} row(s)", "passed": len(got) == len(exp),
         "got": str(len(got)), "expected": str(len(exp))},
    ]
    if ordered:
        match, label = got == exp, "same rows, in the required order"
    else:
        key = lambda r: tuple((v is None, str(type(v)), v if v is not None else 0) for v in r)  # noqa: E731
        try:
            match = sorted(got, key=key) == sorted(exp, key=key)
        except TypeError:
            match = sorted(map(repr, got)) == sorted(map(repr, exp))
        label = "same rows (order ignored)"
    checks.append({"label": label, "passed": match})
    res["checks"] = checks
    res["ok"] = all(c["passed"] for c in checks)
    res["expected_preview"] = {"columns": ecols, "rows": [list(r) for r in erows[:8]]}
    return res
