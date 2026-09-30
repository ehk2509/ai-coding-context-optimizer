"""Tests for the sharded E2E result merge script."""

import importlib.util
from pathlib import Path


def _merge_module():
    """Load the merge script as a module for pure helper tests."""
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "merge_e2e_results.py"
    spec = importlib.util.spec_from_file_location("merge_e2e_results", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_rebases_artifact_paths_to_the_merged_manifest(tmp_path):
    """A merged manifest outside the shard directory must still resolve transcripts."""
    merge = _merge_module()
    shards = tmp_path / "campaign" / "results"
    shards.mkdir(parents=True)
    output_dir = tmp_path / "campaign"
    run = {
        "task": "t",
        "transcripts": ["t-runs.artifacts/t/trial-1/baseline/transcript.jsonl"],
        "agent_patch": "t-runs.artifacts/t/trial-1/baseline/agent.patch",
        "verification": [
            {
                "kind": "swebench_docker",
                "image": "docker.io/swebench/example:latest",
                "stdout": "t-runs.artifacts/t/trial-1/baseline/swebench.stdout",
            }
        ],
    }

    rebased = merge._rebase_run(run, shards, output_dir)

    prefix = "results/t-runs.artifacts/t/trial-1/baseline/"
    assert rebased["transcripts"] == [prefix + "transcript.jsonl"]
    assert rebased["agent_patch"] == prefix + "agent.patch"
    assert rebased["verification"][0]["stdout"] == prefix + "swebench.stdout"
    assert rebased["verification"][0]["image"] == "docker.io/swebench/example:latest"
    assert run["transcripts"] == ["t-runs.artifacts/t/trial-1/baseline/transcript.jsonl"]
    for relative in rebased["transcripts"]:
        assert (output_dir / relative).resolve() == (
            shards / run["transcripts"][0]
        ).resolve()


def test_merge_keeps_paths_when_written_next_to_shards(tmp_path):
    """Merging into the shard directory leaves paths unchanged."""
    merge = _merge_module()
    run = {"transcripts": ["a/transcript.jsonl"], "agent_patch": "/abs/agent.patch"}

    rebased = merge._rebase_run(run, tmp_path, tmp_path)

    assert rebased["transcripts"] == ["a/transcript.jsonl"]
    assert rebased["agent_patch"] == "/abs/agent.patch"
