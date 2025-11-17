# CLAUDE.md — Universal Guardrailed Build Guide (Claude Code in WSL)

> **Role:** Claude Code is the **primary implementer and orchestrator**. It plans, runs commands, generates patches, and opens PRs.
>
> **Delegation:** It may call secondary codegen tools (e.g., Gemini/Codex) for heavy lifting (large codegen, multi-file edits, scaffolding, refactors, bulk tests/fixtures), but Claude remains responsible for the final patches and PRs.
>
> **Source of truth:** **AGENTS.md** (or `TASKS.md`) defines scope. If anything conflicts, **AGENTS.md wins**.
>
> **Runtime:** Execute inside **WSL (Ubuntu)** from the repo root. Shell = **bash**. Editor = **VS Code** (or Visual Studio with WSL integration).


---

## 🎯 Project Snapshot (mirror AGENTS.md)
- **Task:** _(single current task only)_
- **Branch:** `feat/<short-kebab-slug>`
- **Status:** In Progress
- **Next:** _(populated after current PR merges)_

**Work one task at a time.** Do not begin the next task until the current PR is merged.

---

## 🧭 Guardrails (Hallucination Controls)
1) **One task → one PR → merge → next task.**
2) **Scope budget:** ≤ ~300 LOC and ≤ 5 files per PR (unless explicitly allowed).
3) **No invention.** If requirements are ambiguous or missing, implement the **smallest reasonable slice**, add a `TODO(reason)` and proceed.
4) **No secret leakage.** Never place live keys in client code, logs, or patches. Load from server/CI secrets or `.env` (not committed).
5) **No drive‑by refactors.** Keep diffs surgical. Do not rename or relocate files unless the task says so.
6) **Determinism first.** Prefer explicit dependencies, fixed versions/locks, and reproducible commands.
7) **Ask before destructive ops.** Do not drop DBs, rewrite history, or alter CI/prod configs without an explicit instruction in AGENTS.md.
8) **Server is source of truth for sorting/filters.** UI toggles only set params; server applies logic.
9) **Exports include all filtered rows** (ignore pagination) and mirror current server sort.
10) **Stop if any stop‑condition triggers** (see below). Open a PR with findings instead of guessing.

---

## 🔀 Branch & PR Workflow (per task)
> One task → one branch → one PR → merge → next task.

### 0) Start
```bash
# Ensure local is current
git checkout dev && git pull
# Create feature branch
git checkout -b feat/<short-kebab-slug>
```

### 1) Implement (within scope budget)
- Touch ≤ 5 files; keep the patch ≤ ~300 LOC.
- Honor **Contracts** (I/O envelope, sorting, export semantics, error shape).
- Add or update targeted tests only for the touched area.

### 2) Preflight (from repo root)
```bash
# Detect stack & install
# Python
[ -f requirements.txt ] && pip install -r requirements.txt || true
[ -f pyproject.toml ] && pip install -e . || true
# Node
[ -f package-lock.json ] && npm ci || true
[ -f pnpm-lock.yaml ] && corepack enable && pnpm i --frozen-lockfile || true
[ -f yarn.lock ] && yarn install --frozen-lockfile || true
# Go / Rust / Java
[ -f go.mod ] && go mod download || true
[ -f Cargo.toml ] && cargo fetch || true
[ -f pom.xml ] && mvn -q -DskipTests package || true
[ -f build.gradle ] && ./gradlew -q assemble || true

# Lint/format/tests (run what exists)
[ -f .pre-commit-config.yaml ] && pre-commit run -a || true
[ -f pyproject.toml ] && ruff check . || true
[ -f pyproject.toml ] && black --check . || true
[ -f pytest.ini ] && pytest -q || true
[ -f package.json ] && npm test -s || true
[ -f go.mod ] && go test ./... || true
[ -f Cargo.toml ] && cargo test -q || true
```

### 3) Commit
```bash
git add -A
# Conventional Commit style
git commit -m "feat(<area>): short imperative summary"
```

### 4) Push & PR
```bash
git push -u origin HEAD
# Open PR to `dev` with the template below
```

### 5) After Merge
```bash
git checkout dev && git pull
# prune local/remote branch
git branch -d feat/<slug> && git push origin :feat/<slug>
```

### 6) Advance the Queue
- Update **AGENTS.md → CURRENT FOCUS** to the next task and set its branch name.
- Repeat from step 0.

**Branch naming:** `feat/<slug>` for features, `fix/<slug>` for fixes, `chore/<slug>` for chores.

**Protected branches:** Protect `main` (and usually `dev`); require CI pass (format/lint/test/build).

---

## 📐 Contracts (Project-agnostic)
- **WhatsApp pipeline note:** For the WhatsApp transcript project, canonical I/O formats and CLIs are defined in **AGENTS.md**. Treat this section as guidance for any HTTP services or external APIs you add later; it does **not** override AGENTS.md’s file/CLI contracts.
- **Stable I/O envelope** for services/CLIs/APIs:
  ```json
  { "ok": true, "data": <payload>, "error": null, "meta": {"version": "x.y.z"} }

  ```
  On failure: `{ "ok": false, "data": null, "error": {"code":"…","message":"…"} }`.
- **Sorting & filters**: server accepts `?sort=<field>&order=asc|desc` and applies it. Client never sorts authoritative data locally.
- **Pagination**: stable `page`, `page_size`, `total` fields. Exports ignore pagination and include **all filtered rows**.
- **CSV/Excel order**: column order is explicit and stable; changes require a separate task.
- **Config**: read from `.env` (not committed) and/or CI secrets. No plaintext keys in code or tests.
- **Logging**: add concise, structured logs around the new code path only.
- **Error semantics**: never raise raw exceptions to users; map to normalized error codes/messages.

---

## 🤖 Claude Code Solo Loop (per task)
1) **Plan** – Read **AGENTS.md → CURRENT FOCUS**. Output a 3–6 step plan that fits the scope budget.
2) **Preflight** – Run the preflight block and capture outputs for the PR.
3) **Implement** – Produce **unified diffs** (or full files) within limits. Avoid refactors.
4) **Apply** – Apply patch locally. If scope would exceed limits, split into sequential PRs.
5) **Verify** – Provide smoke tests (CLI or HTTP) that prove envelope, sorting, and export semantics.
6) **PR** – Open a PR to `dev` using the template below; include preflight logs and smoke outputs.
7) **Advance** – After merge, update **AGENTS.md CURRENT FOCUS** and stop.

### Patch Output Expectations
- Use fenced ```diff blocks with unified diffs.
- New files: include full path + contents.
- Add `TODO(<ticket or reason>)` for scoped deferrals.

### Smoke‑Test Patterns (choose what fits)
**HTTP API**
```bash
curl -s "http://localhost:PORT/api/resource?sort=created_at" \
  | jq '{ok, data: (.data[:2] // []), meta}
'
curl -s "http://localhost:PORT/api/resource/export?format=csv" | head -n 5
```
**CLI**
```bash
./bin/tool list --sort created_at --format json | jq '{ok, count: (.data|length)}'
./bin/tool export --format csv | head -n 5
```

---

## 🛠️ Environment Bootstrapping (Polyglot)
Claude detects the stack by repo markers and runs only what applies.

- **Python**: `requirements.txt` → `pip install -r`; `pyproject.toml` → `pip install -e .`; run `ruff`, `black --check`, `pytest` if present.
- **Node**: lockfile → `npm ci`/`pnpm i --frozen-lockfile`/`yarn install --frozen-lockfile`; run `npm test` if present.
- **Go**: `go mod download` then `go test ./...`.
- **Rust**: `cargo fetch` then `cargo test`.
- **Java/Kotlin**: `mvn -DskipTests package` or `./gradlew assemble`.
- **Docker**: if `docker-compose*.yml` exists and service is required for tests, run `docker compose up -d <service>`.
- **WSL tips**: ensure LF endings, correct Node/Python versions via NVM/pyenv/asdf, and run commands inside the Linux filesystem (not `/mnt/c`).

---

## 🔁 Task Cues (quick prompts)
**PLAN**
```
Read AGENTS.md → CURRENT FOCUS. Output:
1) Task summary
2) Files to touch (≤5)
3) LOC estimate (≤300)
4) Risks and how to honor Contracts/Guardrails
Do not exceed the current task.
```

**IMPLEMENT**
```
Generate a minimal patch for ONLY the current task.
Rules:
- ≤ ~300 LOC, ≤ 5 files
- Keep I/O envelopes, sort, and export behavior EXACT
- Prefer editing existing files; list any new files up front
- Output UNIFIED DIFFs (```diff fenced). Include a short smoke test.
```

**VERIFY**
```
Provide smoke steps proving:
- Envelope keys present and shaped correctly
- Server-side sort honored (?sort=...)
- Exports return full filtered dataset (not just current page)
```

**PR**
```
Open a PR to dev using the template. Attach preflight logs + smoke outputs.
```

**RECOVER (on failure)**
```
Stop work. Summarize failing preflight/tests, what was attempted, and minimal next step. Open PR with findings instead of guessing.
```

---

## 📦 PR Template
**Task:** N — <title>
**Scope:** files changed (≤ 5), ~LOC
**Why:** 2–5 bullets

#### What changed
- …

#### Preflight output
<lint/format/test logs>

#### Smoke tests
<curl/jq outputs or CLI steps>

#### Limitations / TODO
- …

#### Affected files (≤ 5)
- …

---

## 🛑 Stop Conditions (halt & PR findings)
- Would exceed **LOC/files** budget.
- **Ambiguity** blocks a minimal viable slice.
- **Secrets** missing (cannot run without provisioning).
- **Tests/linters** fail and cannot be fixed within scope.
- **Destructive change** requested without explicit approval in AGENTS.md.
- **CI red** unrelated to the touched area (surface and stop).

---

## ⏱️ Idle / No‑Output Watchdog (opt‑in)
To prevent “hung” local runs without killing healthy work, wrap long‑running commands with a **watchdog** that stops the process if there’s **no activity** for a period, while allowing active servers to continue.

### Principles
- **Idle ≠ wall‑time:** detect *no output* and/or *failing health checks*, not just elapsed time.
- **Graceful first:** send SIGTERM, then SIGKILL if the process ignores shutdown.
- **Liveness signals:** treat any of these as activity:
  - New stdout/stderr lines from the process
  - **HTTP 200** from a health endpoint (e.g., `/healthz`)
  - **Heartbeat file** mtime updated by the app (optional)
- **Safe defaults:** conservative idle window (e.g., 3–5 min), longer hard cap (e.g., 20–60 min).

### Quick options
**A) Minimal wall‑clock guard (least smart):**
```bash
# Kills after 20m; sends TERM then KILL after 10s
# (Does not watch output/health; use only as a backstop.)
timeout --preserve-status --signal=TERM --kill-after=10s 20m your-command
```

**B) Full idle watchdog (recommended):** `scripts/run_with_watchdog.py`
```python
#!/usr/bin/env python3
import argparse, os, signal, subprocess, sys, time, threading, queue, requests

def enqueue(stream, q):
    for line in iter(stream.readline, b""):
        q.put(time.time())
        sys.stdout.buffer.write(line) if stream is sys.stdin else sys.stderr.buffer.write(line)
    stream.close()

def healthy(urls):
    ok=False
    for u in urls:
        try:
            r=requests.get(u, timeout=2)
            if r.status_code==200: ok=True
        except Exception:
            pass
    return ok

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--idle-secs', type=int, default=int(os.getenv('IDLE_SECS', '240')))
    ap.add_argument('--hard-timeout', type=int, default=int(os.getenv('HARD_TIMEOUT', '1800')))
    ap.add_argument('--check-interval', type=int, default=5)
    ap.add_argument('--kill-after', type=int, default=10)
    ap.add_argument('--ready-regex', default=None)
    ap.add_argument('--http-check', action='append', default=[])
    ap.add_argument('--heartbeat-file', default=None)
    ap.add_argument('cmd', nargs=argparse.REMAINDER, help='-- your command and args')
    args=ap.parse_args()

    if args.cmd and args.cmd[0]=='--': args.cmd=args.cmd[1:]
    if not args.cmd: print('need a command after --', file=sys.stderr); return 2

    start=time.time(); last=time.time();
    p=subprocess.Popen(args.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       preexec_fn=os.setsid, bufsize=1, text=False)

    q=queue.Queue()
    t1=threading.Thread(target=enqueue, args=(p.stdout,q), daemon=True); t1.start()
    t2=threading.Thread(target=enqueue, args=(p.stderr,q), daemon=True); t2.start()

    while True:
        try:
            while True:
                last=q.get_nowait();
        except queue.Empty:
            pass

        now=time.time()
        # Treat heartbeat file update as activity
        if args.heartbeat_file and os.path.exists(args.heartbeat_file):
            last=max(last, os.path.getmtime(args.heartbeat_file))
        # Treat healthy HTTP check as activity
        if args.http_check and healthy(args.http_check):
            last=now

        # Hard timeout
        if now-start > args.hard_timeout:
            reason=f"hard-timeout>{args.hard_timeout}s"
            break
        # Idle timeout
        if now-last > args.idle_secs:
            reason=f"idle>{args.idle_secs}s"
            break

        if p.poll() is not None:
            return p.returncode
        time.sleep(args.check_interval)

    # Graceful termination of the whole process group
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline=time.time()+args.kill_after
    while time.time()<deadline and p.poll() is None:
        time.sleep(0.2)
    if p.poll() is None:
        try: os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    print(f"[watchdog] stopped '{' '.join(args.cmd)}' due to {reason}", file=sys.stderr)
    return 124 if 'idle' in reason else 137

if __name__=='__main__':
    sys.exit(main())
```
> Save as `scripts/run_with_watchdog.py` and `pip install requests` in your dev venv. The script mirrors stdout/stderr, treats successful health checks as activity, and kills the **process group** to avoid orphans.

**Usage examples**
```bash
# HTTP server with health check and idle cap
env IDLE_SECS=300 HARD_TIMEOUT=3600 \
python3 scripts/run_with_watchdog.py --http-check http://localhost:3000/healthz -- \
  npm run dev

# CLI that prints intermittently; add a heartbeat file in your code
touch tmp/.hb && \
python3 scripts/run_with_watchdog.py --idle-secs 180 --heartbeat-file tmp/.hb -- \
  python -m mytool long-job

# Docker compose, backstop only
HARD_TIMEOUT=1800 timeout --preserve-status --signal=TERM --kill-after=15s 30m docker compose up
```

**Makefile shim (optional)**
```makefile
.PHONY: dev
DEV_CMD = npm run dev
IDLE_SECS ?= 300
HARD_TIMEOUT ?= 3600

dev:
	python3 scripts/run_with_watchdog.py --http-check http://localhost:3000/healthz -- \
		$(DEV_CMD)
```

**App heartbeat helper (optional)**
- Log a line every 60s: `console.log('[hb]', Date.now())` or `print('[hb]', flush=True)`.
- Touch a file from your app: `fs.utimes('tmp/.hb', new Date(), new Date())` or `Path('tmp/.hb').touch()`.

**Claude Code usage**
- When starting dev servers/tests in its loop, Claude should wrap commands with the watchdog (B) and include the exit reason in PR logs.
- If the watchdog fires, **STOP** work and open a “findings” PR (do not guess).

---

## ✅ Final Checklist (per task)
- [ ] Plan fits scope (≤ 6 steps) and mirrors AGENTS.md
- [ ] Preflight ran; logs captured
- [ ] Patch is surgical; no drive‑by refactors or secrets
- [ ] Envelope/sort/export semantics verified with smoke tests
- [ ] PR opened with template + artifacts
- [ ] NEXT task set in AGENTS.md, then stop

