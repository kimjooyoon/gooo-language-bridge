"""Capture a requested native 32-bit Cast observation, retaining semantic failures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "github.com/spf13/cast"
REPOSITORY = "https://github.com/spf13/cast.git"
REVISIONS = {
    "base": "fc670a425e3a64c4e872fa732cf0b6971e4dcbdb",
    "proposal": "9b5719a3d52e3d211cf6baaba423da07c1e39da9",
}
PARENTS = ("TestNumber", "TestBridge386Runtime", "TestBridge386Bounds")
BOUNDS = ("int/min", "int/max", "int/overflow", "int/underflow",
          "uint/max", "uint/overflow", "int64/min", "int64/max", "uint64/max")
MARKER = "CAST386_RUNTIME "


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("nonfinite JSON value: " + value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def parse_capture(text: str, exit_code: int) -> dict:
    """Require actual runtime and complete results; a failed assertion is evidence."""
    if type(exit_code) is not int or exit_code not in (0, 1):
        raise ValueError("Go exit code must be integer zero or one")
    tests, bounds, packages, witnesses = {}, {}, [], []
    skipped = 0
    groups = {name.split("/")[0] for name in BOUNDS}
    for line in text.splitlines():
        if not line.strip():
            raise ValueError("blank Go JSON event")
        row = strict_json(line)
        if not isinstance(row, dict):
            raise ValueError("Go JSON event must be an object")
        output = row.get("Output", "")
        if not isinstance(output, str):
            raise ValueError("Go output must be text")
        if MARKER in output:
            if (row.get("Action"), row.get("Package"), row.get("Test")) != (
                    "output", PACKAGE, "TestBridge386Runtime"):
                raise ValueError("runtime marker has incorrect event context")
            if output.count(MARKER) != 1:
                raise ValueError("duplicate runtime marker")
            witnesses.append(strict_json(output.split(MARKER, 1)[1].strip()))
        if row.get("Package") != PACKAGE:
            continue
        action, test = row.get("Action"), row.get("Test")
        if action == "skip":
            skipped += 1
        if action not in ("pass", "fail", "skip"):
            continue
        if test is None:
            packages.append(action)
        elif test in PARENTS:
            if action == "skip" or test in tests:
                raise ValueError("missing or duplicate required parent result")
            tests[test] = action
        elif test.startswith("TestBridge386Bounds/"):
            suffix = test.removeprefix("TestBridge386Bounds/")
            if suffix in groups:
                continue
            if suffix not in BOUNDS or action == "skip" or suffix in bounds:
                raise ValueError("invalid, skipped, or duplicate boundary result")
            bounds[suffix] = action
    if len(witnesses) != 1:
        raise ValueError("exactly one runtime witness is required")
    runtime = witnesses[0]
    expected = {"go_version": "go1.27.3", "os": "linux", "arch": "386", "int_bits": 32}
    if (not isinstance(runtime, dict) or runtime != expected
            or type(runtime.get("int_bits")) is not int):
        raise ValueError("runtime witness must be Go1.27.3 Linux/386 with 32-bit int")
    if set(tests) != set(PARENTS) or tests["TestBridge386Runtime"] != "pass":
        raise ValueError("all required parents and passing runtime witness are required")
    if set(bounds) != set(BOUNDS):
        raise ValueError("all nine boundary results are required")
    if packages != ["pass" if exit_code == 0 else "fail"]:
        raise ValueError("one package result must match the Go exit code")
    if tests["TestBridge386Bounds"] != ("fail" if "fail" in bounds.values() else "pass"):
        raise ValueError("boundary parent disagrees with boundary results")
    if exit_code == 0 and "fail" in tests.values():
        raise ValueError("passing package contradicts required test failure")
    return {"runtime": runtime, "tests": tests, "bounds": bounds,
            "go_exit_code": exit_code, "skipped_events": skipped}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "native-observations/cast-310-386")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema": "cast-310-linux-386-observation-v1", "state": "FAILED_INCOMPLETE",
               "source_revision": os.environ.get("GITHUB_SHA"),
               "run_id": os.environ.get("GITHUB_RUN_ID"),
               "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
               "upstream_repository": REPOSITORY, "steps": [], "observations": {}}
    inherited = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL",
                 "GOCACHE", "GOMODCACHE", "SSL_CERT_FILE", "SSL_CERT_DIR")
    env = {key: os.environ[key] for key in inherited if key in os.environ}
    fixed = dict(CGO_ENABLED="0", GOOS="linux", GOARCH="386", GO386="sse2",
                 GOENV="off", GOTOOLCHAIN="local", GOWORK="off",
                 GOFLAGS="-mod=readonly", GOMAXPROCS="2",
                 GOPROXY="https://proxy.golang.org,direct", GOSUMDB="sum.golang.org")
    env.update(fixed)

    def run(command, cwd, name, *, expected=(0,), timeout=180):
        stdout, stderr = output / (name + ".stdout"), output / (name + ".stderr")
        step = {"name": name, "argv": command, "stdout": stdout.name, "stderr": stderr.name}
        receipt["steps"].append(step)
        started = time.monotonic()
        with stdout.open("xb") as out, stderr.open("xb") as err:
            try:
                result = subprocess.run(command, cwd=cwd, env=env, stdout=out, stderr=err,
                                        timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                step["timeout_seconds"] = timeout
                raise ValueError(name + " timed out; partial output retained") from None
            finally:
                step["elapsed_seconds"] = round(time.monotonic() - started, 3)
        step["exit_code"] = result.returncode
        if result.returncode not in expected:
            raise ValueError(name + " exited " + str(result.returncode))
        return stdout.read_text(), result.returncode

    try:
        if platform.system() != "Linux":
            raise ValueError("this experiment requires a Linux host able to execute 386 binaries")
        probe = ROOT / "observations/cast-310-386/probe_test.go"
        (output / "probe_test.go").write_bytes(probe.read_bytes())
        receipt["probe_sha256"] = sha256(probe)
        receipt["environment"] = fixed
        receipt["inherited_environment_keys"] = sorted(set(env) - set(fixed))
        with tempfile.TemporaryDirectory(prefix="cast-386-") as temporary:
            for label, revision in REVISIONS.items():
                checkout = Path(temporary) / label
                checkout.mkdir()
                run(["git", "init", "--quiet"], checkout, label + "-init")
                run(["git", "fetch", "--depth=1", "--no-tags", REPOSITORY, revision],
                    checkout, label + "-fetch")
                run(["git", "checkout", "--detach", "--quiet", "FETCH_HEAD"],
                    checkout, label + "-checkout")
                actual, _ = run(["git", "rev-parse", "HEAD"], checkout, label + "-revision")
                if actual.strip() != revision:
                    raise ValueError(label + " source revision mismatch")
                tracked, _ = run(["git", "ls-files", "-z"], checkout, label + "-tracked")
                files = [name for name in tracked.split("\0") if name]
                original = {name: sha256(checkout / name) for name in files}
                injected = checkout / "gooo_cast386_observer_test.go"
                with injected.open("xb") as handle:
                    handle.write(probe.read_bytes())
                command = ["go", "test", "-p=2", "-count=1", "-timeout=45s", "-json",
                           "-run", "^(TestNumber|TestBridge386Runtime|TestBridge386Bounds)$", "."]
                raw, code = run(command, checkout, label + "-tests", expected=(0, 1))
                if original != {name: sha256(checkout / name) for name in files}:
                    raise ValueError(label + " tracked source changed during observation")
                result = parse_capture(raw, code)
                result.update(revision=revision, source_files_sha256=original,
                              test_command=command, probe_sha256=sha256(injected))
                receipt["observations"][label] = result
        receipt["state"] = "OBSERVED"
        receipt["meaning"] = "Complete native observation; semantic test outcomes are recorded separately."
    except (ValueError, OSError) as error:
        receipt["first_failure"] = str(error)
    finally:
        receipt["files_sha256"] = {path.name: sha256(path) for path in sorted(output.iterdir())
                                   if path.is_file()}
        (output / "observation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"state": receipt["state"], "receipt": str(output / "observation.json"),
                      "first_failure": receipt.get("first_failure")}))
    return 0 if receipt["state"] == "OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
