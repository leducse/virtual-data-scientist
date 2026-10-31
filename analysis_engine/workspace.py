"""Local workspace: immutable data versions and transactional per-run state."""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from analysis_engine.ingestion import InputError, parse_table, write_parquet
from analysis_engine.planning import local_plan
from analysis_engine.tabular import quick_result, RECIPE_SHA256, RECIPE_SOURCE

ACTIVE = ("queued", "running", "reviewing")


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path = self.root / "workspace.sqlite"
        self.threads = []
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, owner TEXT NOT NULL, doc TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, dataset_id TEXT NOT NULL,
                  request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL, doc TEXT NOT NULL,
                  UNIQUE(owner,request_key));
            """)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("PRAGMA secure_delete=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def recover(self):
        # shortcut: one local server owns workers; use durable leases/queue before multi-process cloud hosting.
        with self.connect() as con:
            rows = con.execute("SELECT id,doc FROM runs WHERE status IN ('queued','running','reviewing')").fetchall()
            for run_id, raw in rows:
                doc = json.loads(raw)
                doc.update(status="interrupted", stage="Server restarted; retry with a new request key.", error={"code": "worker_interrupted", "message": "Previous execution was interrupted; it was not duplicated."})
                con.execute("UPDATE runs SET status=?,doc=? WHERE id=?", (doc["status"], json.dumps(doc), run_id))
                scratch = self.root / doc["dataset_id"] / run_id
                if scratch.exists():
                    shutil.rmtree(scratch)

    def dataset(self, owner, dataset_id):
        with self.connect() as con:
            row = con.execute("SELECT doc FROM datasets WHERE id=? AND owner=?", (dataset_id, owner)).fetchone()
        if not row or json.loads(row[0]).get("deleted"):
            raise InputError("Dataset not found.", "not_found")
        return json.loads(row[0])

    def list(self, owner):
        with self.connect() as con:
            datasets = [json.loads(r[0]) for r in con.execute("SELECT doc FROM datasets WHERE owner=? ORDER BY rowid DESC", (owner,))]
            runs = [json.loads(r[0]) for r in con.execute("SELECT doc FROM runs WHERE owner=? ORDER BY rowid DESC LIMIT 100", (owner,))]
        return {"datasets": [d for d in datasets if not d.get("deleted")], "runs": runs, "mode": "local_demo", "cloud_enabled": False}

    def ingest(self, owner, name, raw, sheet=None, header_row=None, question=None):
        started = time.monotonic()
        table, profile = parse_table(name, raw, sheet, header_row, question or "")
        dataset_id = uuid.uuid4().hex
        folder = self.root / dataset_id
        folder.mkdir(mode=0o700)
        try:
            (folder / "source").write_bytes(raw)
            write_parquet(table, folder / "dataset.parquet")
            doc = {"id": dataset_id, "name": Path(name).name[:200], "version": dataset_id, "sha256": hashlib.sha256(raw).hexdigest(),
                   "created_at": time.time(), "profile": profile, "ready": True, "ingestion_version": "csv-xlsx-v1",
                   "parquet_sha256": hashlib.sha256((folder / "dataset.parquet").read_bytes()).hexdigest(),
                   "timing_ms": {"ingestion": round((time.monotonic()-started)*1000, 2)}, "storage": "local_immutable_parquet"}
            with self.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                count = con.execute("SELECT count(*) FROM datasets WHERE owner=? AND json_extract(doc,'$.deleted') IS NULL", (owner,)).fetchone()[0]
                if count >= 10:
                    raise InputError("Local limit: 10 datasets. Delete an old version before uploading.", "capacity_exceeded")
                con.execute("INSERT INTO datasets VALUES(?,?,?)", (dataset_id, owner, json.dumps(doc)))
            return doc
        except Exception:
            shutil.rmtree(folder)
            raise

    def run(self, owner, run_id):
        with self.connect() as con:
            row = con.execute("SELECT doc FROM runs WHERE id=? AND owner=?", (run_id, owner)).fetchone()
        if not row:
            raise InputError("Run not found.", "not_found")
        doc = json.loads(row[0])
        self.dataset(owner, doc["dataset_id"])
        return doc

    def update(self, owner, run_id, **updates):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT doc,status FROM runs WHERE id=? AND owner=?", (run_id, owner)).fetchone()
            if not row or row[1] not in ACTIVE:
                return False
            doc = json.loads(row[0])
            doc.update(updates, updated_at=time.time())
            con.execute("UPDATE runs SET status=?,doc=? WHERE id=?", (doc["status"], json.dumps(doc, allow_nan=False), run_id))
        return True

    def submit(self, owner, payload):
        if payload.get("research_requirement", "none") != "none":
            raise InputError("External research is not enabled in this local workspace.", "research_unavailable")
        dataset = self.dataset(owner, payload.get("dataset_id"))
        plan = local_plan(dataset, payload)
        key = str(payload.get("request_key", ""))
        if not key or len(key) > 100:
            raise InputError("A request key of 1–100 characters is required.")
        fingerprint = hashlib.sha256(json.dumps(plan.model_dump(exclude={"revision"}), sort_keys=True).encode()).hexdigest()
        run_id = uuid.uuid4().hex
        doc = {"id": run_id, "dataset_id": dataset["id"], "question": plan.question, "plan": plan.model_dump(),
               "status": "queued", "stage": "queued", "created_at": time.time(), "trace_id": run_id,
               "execution_mode": "local_trusted_recipe", "recipe_sha256": RECIPE_SHA256, "result": None}
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            old = con.execute("SELECT fingerprint,doc FROM runs WHERE owner=? AND request_key=?", (owner,key)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise InputError("Request key already belongs to a different plan.", "idempotency_conflict")
                return json.loads(old[1])
            total, mine = con.execute("SELECT count(*),sum(owner=?) FROM runs WHERE status IN ('queued','running','reviewing') AND json_extract(doc,'$.plan.tier')='deep'", (owner,)).fetchone()
            if plan.tier == "deep" and (total >= 2 or (mine or 0) >= 1):
                raise InputError("Deep capacity is occupied (one per owner, two total). Try again after completion.", "capacity_exceeded")
            active_quick = con.execute("SELECT count(*) FROM runs WHERE status IN ('queued','running','reviewing') AND json_extract(doc,'$.plan.tier')='quick'").fetchone()[0]
            if plan.tier == "quick" and active_quick >= 8:
                raise InputError("Quick capacity is occupied. Try again shortly.", "capacity_exceeded")
            count = con.execute("SELECT count(*) FROM runs WHERE owner=?", (owner,)).fetchone()[0]
            if count >= 100:
                raise InputError("Local limit: 100 runs. Delete old datasets to free their results.", "capacity_exceeded")
            previous = con.execute("SELECT id,doc FROM runs WHERE owner=? AND dataset_id=? ORDER BY rowid DESC LIMIT 1", (owner,dataset["id"])).fetchone()
            if previous:
                doc["prior_run_id"] = previous[0]
                doc["plan"]["revision"] = json.loads(previous[1])["plan"]["revision"] + 1
            con.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (run_id,owner,dataset["id"],key,fingerprint,"queued",json.dumps(doc)))
        if plan.tier == "quick":
            try:
                self.update(owner,run_id,status="running",stage="querying Parquet")
                result = quick_result(self.root / dataset["id"] / "dataset.parquet", plan)
                self.finish(owner,run_id,result)
            except Exception as exc:
                self.fail(owner,run_id,exc)
        else:
            thread = threading.Thread(target=self.deep, args=(owner,run_id,plan.model_copy(update={"revision": doc["plan"]["revision"]})), daemon=True)
            self.threads = [t for t in self.threads if t.is_alive()]
            self.threads.append(thread)
            thread.start()
        return self.run(owner,run_id)

    def finish(self, owner, run_id, result):
        run = self.run(owner,run_id)
        source = RECIPE_SOURCE
        if result.get("recipe_sha256") != run["recipe_sha256"]:
            raise InputError("Recipe changed during execution; restart and submit a new run.", "code_version_changed")
        result["evidence"] = {"dataset_version": run["dataset_id"], "source_sha256": self.dataset(owner,run["dataset_id"])["sha256"],
                              "parquet_sha256": self.dataset(owner,run["dataset_id"])["parquet_sha256"], "plan": run["plan"], "recipe_sha256": hashlib.sha256(source.encode()).hexdigest(), "recipe_source": source,
                              "reproduction": "Use the saved recipe as analysis_engine/tabular.py with the saved plan and original immutable Parquet. No generated Python was executed."}
        result.setdefault("timing_ms", {})["end_to_end"] = round((time.time()-run["created_at"])*1000, 2)
        self.update(owner,run_id,status="succeeded",stage="numerical review passed",result=result)

    def fail(self, owner, run_id, exc):
        self.update(owner,run_id,status="failed",stage="analysis failed",error={"code": getattr(exc,"code","analysis_failed"),
                    "message": str(exc) if isinstance(exc, InputError) else "Analysis could not finish. Review input and retry; details are excluded from public errors."})

    def deep(self, owner, run_id, plan):
        run_folder = self.root / plan.dataset_version / run_id
        process = None
        try:
            self.update(owner,run_id,status="running",stage="starting bounded local recipe")
            run_folder.mkdir(mode=0o700)
            (run_folder / "input.json").write_text(plan.model_dump_json())
            env = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
            process = subprocess.Popen([sys.executable, "-m", "analysis_engine.local_worker", str(run_folder / "input.json")],
                                       cwd=Path(__file__).resolve().parents[1], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic()+plan.max_seconds
            while process.poll() is None:
                run = self.run(owner,run_id)
                if run["status"] not in ACTIVE:
                    return
                if time.monotonic() > deadline:
                    raise InputError("The job exceeded its execution deadline.", "deadline_exceeded")
                stage_path = run_folder / "stage.txt"
                if stage_path.exists():
                    self.update(owner,run_id,stage=stage_path.read_text()[:100])
                time.sleep(.1)
            data = json.loads((run_folder / "output.json").read_text())
            if "error" in data:
                raise InputError(data["error"]["message"], data["error"]["code"])
            self.update(owner,run_id,status="reviewing",stage="checking persisted evidence")
            self.finish(owner,run_id,data)
        except Exception as exc:
            self.fail(owner,run_id,exc)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            # Worker scratch is ephemeral; durable evidence is committed atomically in SQLite.
            if run_folder.exists():
                shutil.rmtree(run_folder)

    def cancel(self, owner, run_id):
        self.run(owner,run_id)
        self.update(owner,run_id,status="cancelled",stage="Cancellation requested; bounded worker is stopping.")
        return self.run(owner,run_id)

    def delete(self, owner, dataset_id):
        self.dataset(owner,dataset_id)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("UPDATE datasets SET doc=? WHERE owner=? AND id=?", (json.dumps({"id":dataset_id,"deleted":True}),owner,dataset_id))
            con.execute("DELETE FROM runs WHERE owner=? AND dataset_id=?", (owner,dataset_id))
        # Access is revoked before physical purge. Workers cannot publish to deleted rows.
        folder = self.root / dataset_id
        if folder.exists():
            shutil.rmtree(folder)
        return {"deleted": True, "dataset_id": dataset_id, "retention": "Active local copies purged; external backups are outside this demo."}
