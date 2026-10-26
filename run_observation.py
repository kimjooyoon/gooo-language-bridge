#!/usr/bin/env python3
"""One build and five bounded subprocesses; no baseline or inline-cycle run."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source"
SDK = Path("/Users/alice/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.27.3.darwin-arm64")
REVISION = "ad54769aba4d63f437e1df88bd9bc16072fd00e7"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def tracked_snapshot():
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    assert actual == REVISION, actual
    index = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=SOURCE)
    result = {}
    for record in index.split(b"\0"):
        if not record:
            continue
        metadata, filename = record.split(b"\t", 1)
        mode, expected, stage = metadata.split()
        assert stage == b"0" and mode != b"160000"
        path = SOURCE / os.fsdecode(filename)
        data = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
        object_id = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert object_id == expected.decode(), str(path)
        result[os.fsdecode(filename)] = hashlib.sha256(data).hexdigest()
    assert not subprocess.check_output(["git", "diff", "HEAD", "--"], cwd=SOURCE)
    return result

ENV = {k: os.environ[k] for k in ("HOME", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR") if k in os.environ}
ENV.update({"PATH": str(SDK / "bin") + ":/usr/bin:/bin:/usr/sbin:/sbin", "GOROOT": str(SDK),
            "GOTOOLCHAIN": "local", "GOWORK": "off", "GOENV": "off", "GOPROXY": "off", "GOSUMDB": "off",
            "GOFLAGS": "-mod=readonly", "GOMAXPROCS": "2", "CGO_ENABLED": "0", "GOTRACEBACK": "single"})

def alive_group(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False

def run(label, argv, deadline, diagnostic=False):
    start = time.monotonic()
    events = []
    exceeded = False
    with (ROOT / (label + ".stdout")).open("wb") as stdout, (ROOT / (label + ".stderr")).open("wb") as stderr:
        child = subprocess.Popen(argv, cwd=SOURCE, env=ENV, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            try:
                child.wait(timeout=deadline)
            except subprocess.TimeoutExpired:
                exceeded = True
                sig = signal.SIGQUIT if diagnostic else signal.SIGKILL
                events.append({"signal": signal.Signals(sig).name, "seconds": round(time.monotonic() - start, 6)})
                try:
                    os.killpg(child.pid, sig)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    events.append({"signal": "SIGKILL", "seconds": round(time.monotonic() - start, 6)})
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=2)
        finally:
            if alive_group(child.pid):
                events.append({"signal": "SIGKILL", "reason": "final process-group cleanup"})
                os.killpg(child.pid, signal.SIGKILL)
            if child.poll() is None:
                child.wait(timeout=2)
    result = {"label": label, "argv": argv, "deadline_seconds": deadline,
              "deadline_exceeded": exceeded, "exit_code": child.returncode, "signals": events,
              "seconds": round(time.monotonic() - start, 6), "process_group_closed": not alive_group(child.pid),
              "stdout_sha256": sha(ROOT / (label + ".stdout")), "stderr_sha256": sha(ROOT / (label + ".stderr"))}
    assert result["process_group_closed"], result
    return result

def main():
    assert not (ROOT / "observation.json").exists(), "Do not silently rerun/overwrite an observation"
    before = tracked_snapshot()
    assert (ROOT / "observer.go").read_bytes() == (SOURCE / "gooo-review-observer/main.go").read_bytes()
    report = {"observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "revision": REVISION,
              "source_before": before, "environment": ENV, "observer_sha256": sha(ROOT / "observer.go"),
              "supervisor_sha256": sha(Path(__file__)), "base_executed": False, "inline_cycle_executed": False,
              "scope": "Standalone default-Marshal observer, not full suite/race/benchmarks/capability validation",
              "memory_limit_note": "32MiB Go memory target is soft; 8MiB max goroutine stack is separate; external deadline enforced",
              "runs": []}
    def save():
        (ROOT / "observation.json").write_text(json.dumps(report, indent=2) + "\n")
    try:
        report["runs"].append(run("go-version", [str(SDK / "bin/go"), "version"], 5))
        build = run("build", [str(SDK / "bin/go"), "build", "-buildvcs=false", "-p=2", "-o", str(ROOT / "observer"), "./gooo-review-observer"], 30)
        report["runs"].append(build)
        assert build["exit_code"] == 0 and not build["deadline_exceeded"], build
        report["binary_sha256"] = sha(ROOT / "observer")
        report["binary_bytes"] = (ROOT / "observer").stat().st_size
        for case in ("ordinary-map", "self-map", "shared-acyclic-pointer", "nil-values", "pointer-interface-cycle"):
            observed = run(case, [str(ROOT / "observer"), case], 0.75, diagnostic=True)
            report["runs"].append(observed)
            observed["output"] = [json.loads(line) for line in (ROOT / (case + ".stdout")).read_text().splitlines()]
            save()
        report["source_after"] = tracked_snapshot()
        assert report["source_after"] == before
        report["completed"] = True
    finally:
        save()
    print(json.dumps({"revision": REVISION, "completed": report["completed"], "tracked_files": len(before), "runs": report["runs"]}, indent=2))

if __name__ == "__main__":
    main()
