"""Sandbox-ish runner: executes one exercise attempt in a fresh Python process.

Reads a JSON job on stdin: {"code", "setup", "checks", "mode"}.
Writes a single JSON result line on the real stdout, prefixed with a marker.
"""
import contextlib
import io
import json
import math
import sys
import traceback

MARKER = "@@RESULT@@"


def same(a, b):
    """Equality with float tolerance and numpy/pandas awareness."""
    try:
        import pandas as pd
        if isinstance(b, (pd.DataFrame, pd.Series)):
            if type(a) is not type(b):
                return False
            try:
                if isinstance(b, pd.DataFrame):
                    pd.testing.assert_frame_equal(a, b, check_dtype=False, check_exact=False,
                                                  atol=1e-6, check_names=False)
                else:
                    pd.testing.assert_series_equal(a, b, check_dtype=False, check_exact=False,
                                                   atol=1e-6, check_names=False)
                return True
            except AssertionError:
                return False
    except ImportError:
        pass
    try:
        import numpy as np
        if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
            a2, b2 = np.asarray(a), np.asarray(b)
            if a2.shape != b2.shape:
                return False
            if a2.dtype.kind in "fc" or b2.dtype.kind in "fc":
                return bool(np.allclose(a2, b2, atol=1e-6, equal_nan=True))
            return bool((a2 == b2).all())
        if isinstance(a, np.generic):
            a = a.item()
        if isinstance(b, np.generic):
            b = b.item()
    except ImportError:
        pass
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b and type(a) is type(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def short(value, limit=400):
    try:
        text = repr(value)
    except Exception as exc:  # noqa: BLE001
        text = f"<unprintable: {exc}>"
    return text if len(text) <= limit else text[:limit] + " …"


def clean_tb():
    """Traceback without the runner's own frames."""
    etype, evalue, tb = sys.exc_info()
    frames = [f for f in traceback.extract_tb(tb) if f.filename in ("<your code>", "<setup>", "<check>")]
    lines = traceback.format_list(frames) if frames else []
    return "".join(lines) + "".join(traceback.format_exception_only(etype, evalue))


def main():
    job = json.loads(sys.stdin.read())
    real_stdout = sys.stdout
    buf = io.StringIO()
    ns = {"__name__": "__main__"}
    result = {"ok": True, "stdout": "", "error": None, "checks": []}

    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            if job.get("setup"):
                exec(compile(job["setup"], "<setup>", "exec"), ns)
            exec(compile(job["code"], "<your code>", "exec"), ns)
        except BaseException:  # noqa: BLE001 - report everything, incl. SystemExit
            result["ok"] = False
            result["error"] = clean_tb()

        if result["ok"] and job.get("mode") == "check":
            for c in job.get("checks", []):
                label = c.get("label") or c.get("call") or c.get("assert")
                row = {"label": label, "passed": False}
                try:
                    if "call" in c:
                        got = eval(compile(c["call"], "<check>", "eval"), ns)
                        expected = eval(compile(c["expected"], "<check>", "eval"), ns)
                        row["got"] = short(got)
                        row["expected"] = short(expected)
                        row["passed"] = bool(same(got, expected))
                    else:
                        row["passed"] = bool(eval(compile(c["assert"], "<check>", "eval"), ns))
                except BaseException:  # noqa: BLE001
                    row["error"] = clean_tb().strip().splitlines()[-1]
                result["checks"].append(row)
            result["ok"] = all(r["passed"] for r in result["checks"])

    out = buf.getvalue()
    result["stdout"] = out if len(out) <= 20000 else out[:20000] + "\n… (output truncated)"
    real_stdout.write(MARKER + json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
