"""Validate the recorded observation without executing Go again."""
from pathlib import Path
import datetime
import hashlib
import json

root = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = json.loads((root / "observation.json").read_text())
assert report["completed"]
assert report["revision"] == "ad54769aba4d63f437e1df88bd9bc16072fd00e7"
assert report["source_before"] == report["source_after"]
assert len(report["source_after"]) == 122
assert sha(root / "observer.go") == report["observer_sha256"]
assert sha(root / "run_observation.py") == report["supervisor_sha256"]
assert (root / "observer.go").read_bytes() == (root / "source/gooo-review-observer/main.go").read_bytes()
assert sha(root / "observer") == report["binary_sha256"]
assert not report["base_executed"] and not report["inline_cycle_executed"]
by_case = {r["label"]: r for r in report["runs"]}
assert len(by_case) == 7
for name, run in by_case.items():
    assert run["process_group_closed"]
    for stream in ("stdout", "stderr"):
        assert sha(root / (name + "." + stream)) == run[stream + "_sha256"]
    if name in ("go-version", "build"):
        assert run["exit_code"] == 0 and not run["deadline_exceeded"] and not run["signals"]
        continue
    output = [json.loads(line) for line in (root / (name + ".stdout")).read_text().splitlines()]
    assert output == run["output"]
    assert output[0]["phase"] == "call_start" and output[0]["case"] == name
    assert (output[0]["go"], output[0]["os"], output[0]["arch"], output[0]["int_bits"]) == ("go1.27.3", "darwin", "arm64", 64)
    if name == "pointer-interface-cycle":
        assert len(output) == 1 and run["deadline_exceeded"] and run["exit_code"] == 2
        assert run["signals"][0]["signal"] == "SIGQUIT"
        trace = (root / (name + ".stderr")).read_text()
        for frame in ("SIGQUIT: quit", "go-toml/v2.resolve", "marshaler.go:435", "isTableLike", "entryIsTable", "encodeTableEntries"):
            assert frame in trace, frame
        continue
    assert run["exit_code"] == 0 and not run["deadline_exceeded"] and not run["signals"]
    assert len(output) == 2 and output[1]["phase"] == "returned"
    returned = output[1]
    if name == "self-map":
        assert "encountered a cycle" in returned["error"] and returned["encoded"] == ""
    else:
        expected = {"ordinary-map": {"answer": 7}, "shared-acyclic-pointer": {"a": 7, "b": 7}, "nil-values": {"nil_pointer": 0}}[name]
        assert returned["error"] == "" and "decode_error" not in returned and returned["decoded"] == expected
result = {"validated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "passed": True,
          "observation_sha256": sha(root / "observation.json"), "validator_sha256": sha(Path(__file__)),
          "checks": ["122 tracked source files unchanged", "observer, injected copy, supervisor and binary unchanged",
                     "all 14 runtime/build/version raw log hashes match", "four controls match expectations",
                     "cycle started, never returned before deadline, SIGQUIT stack reaches resolve",
                     "all subprocess groups closed", "no baseline or inline-cycle execution"],
          "native_calls_total_seconds": round(sum(r["seconds"] for r in report["runs"]), 6),
          "interpretation": "cycle exit 2 is supervisor-triggered SIGQUIT, not a returned library error; deadline measured from subprocess start"}
(root / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
