// Runs Python and SQL with Pyodide, off the page's main thread so a stuck loop can be stopped.
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

let py = null;
const ready = (async () => {
  py = await loadPyodide();
  for (const f of ["runner.py", "runtime.py"]) {
    py.FS.writeFile(f, await (await fetch(f)).text());
  }
  py.runPython("import sys; sys.path.insert(0, '.'); import runtime");
  postMessage({ type: "ready" });
})().catch(e => postMessage({ type: "failed", error: String(e) }));

let sqlLoaded = false;
onmessage = async ({ data: job }) => {
  try {
    await ready;
    const rt = py.pyimport("runtime");
    let res;
    if (job.lang === "sql") {
      if (!sqlLoaded) { await py.loadPackage("sqlite3"); sqlLoaded = true; }
      res = rt.run_sql(job.seed, job.code, job.solution ?? null, !!job.ordered);
    } else {
      // pandas / numpy are downloaded the first time an exercise imports them
      await py.loadPackagesFromImports((job.setup || "") + "\n" + job.code);
      res = rt.run_python(job.code, job.setup || "", py.toPy(job.checks || []), job.mode);
    }
    postMessage({ type: "result", id: job.id, res: res.toJs({ dict_converter: Object.fromEntries }) });
    res.destroy();
  } catch (e) {
    postMessage({ type: "result", id: job.id, res: { ok: false, error: String(e) } });
  }
};
