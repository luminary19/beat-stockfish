"""Offline recovery regressions; only lock tests launch real, inert Python children."""
from __future__ import annotations

import copy
import fcntl
import importlib.util
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


_SPEC = importlib.util.spec_from_file_location(
    "campaign_recovery_under_test", Path(__file__).with_name("campaign.py"))
campaign = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(campaign)
REAL_POPEN = subprocess.Popen


def proposal():
    return dict(opening=campaign.OPENING.replace("your ability", "your personal ability"),
                asset=None, hypothesis="Neutral wording changes behavior.",
                prediction="Three complete clean episodes.", ablation="Compare wording.")


def state_fixture():
    return dict(status="initialized", stop_reason=None, historical_fingerprints={},
                candidates={}, batches=[], image_id="offline-image")


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        Path("/tmp/opencode").mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="recovery-test-", dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.a = self.root / "autoresearch"
        self.a.mkdir()
        for key, value in dict(ROOT=self.root, A=self.a, LOGS=self.root / "logs",
                               STOP=self.a / "STOP", LOCK_FD=None, NATIVE_CHILD=None).items():
            self.patch(campaign, key, value)
        for name in ("Popen", "run", "check_output", "check_call", "call"):
            self.patch(campaign.subprocess, name,
                       side_effect=AssertionError("Unexpected subprocess: offline test"))
        self.patch(campaign, "git", side_effect=AssertionError("Unexpected Git"))
        self.commit = self.patch(campaign, "commit", return_value="offline-protocol-commit")
        self.patch(campaign.signal, "signal")
        self.patch(campaign, "report")
        self.patch(campaign, "frozen_files", return_value=[self.a / "original-task.txt"])
        self.patch(campaign.importlib.metadata, "version", return_value="offline-version")
        (self.a / "original-task.txt").write_text(campaign.OPENING + "\nFixed task body.\n")

    def patch(self, target, name, *args, **kwargs):
        patcher = mock.patch.object(target, name, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def cached_tick(self, returncode, events):
        d = self.a / "ticks" / "t0001"
        campaign.writej(d / "started.json", {"tick": 1})
        campaign.writej(d / "finished.json", {"returncode": returncode})
        campaign.writej(d / "proposal.json", {"candidates": [proposal()]})
        (d / "events.jsonl").write_text("\n".join(map(json.dumps, events)) + "\n")
        return d

    def test_cached_nonzero_completion_does_not_consume_proposal(self):
        d = self.cached_tick(7, [])
        original = (d / "proposal.json").read_bytes()
        state = state_fixture()
        before = copy.deepcopy(state)
        with mock.patch.object(campaign, "apply_audits") as audits:
            with self.assertRaisesRegex(RuntimeError, "Native tick failed"):
                campaign.native_tick(state)
        audits.assert_not_called()
        self.assertEqual(state, before)
        self.assertEqual((d / "proposal.json").read_bytes(), original)
        self.assertFalse((d / "accepted.json").exists())
        self.commit.assert_not_called()
        campaign.subprocess.Popen.assert_not_called()

    def test_cached_quota_completion_does_not_consume_even_with_success_exit(self):
        error = {"code": "insufficient_quota", "message": "Quota exhausted"}
        for rc in (0, 9):
            with self.subTest(returncode=rc):
                d = self.cached_tick(rc, [{"type": "error", "error": error}])
                original = (d / "proposal.json").read_bytes()
                state = state_fixture()
                with mock.patch.object(campaign, "apply_audits") as audits:
                    self.assertIsNone(campaign.native_tick(state))
                audits.assert_not_called()
                self.assertEqual(state["status"], "quota_exhausted")
                self.assertEqual(state["stop_reason"], "quota_exhausted")
                self.assertEqual(state["batches"], [])
                self.assertEqual(state["candidates"], {})
                self.assertEqual(campaign.readj(self.a / "research-state.json"), state)
                self.assertEqual(campaign.readj(d / "typed-error.json"), error)
                self.assertEqual((d / "proposal.json").read_bytes(), original)
                self.assertFalse((d / "accepted.json").exists())
        self.commit.assert_not_called()
        campaign.subprocess.Popen.assert_not_called()

    def test_committed_freeze_recovers_from_fresh_state_and_journal_idempotently(self):
        class PowerLoss(BaseException):
            pass

        initial = state_fixture()
        state_path = self.a / "research-state.json"
        journal = self.a / "freeze-transaction.json"
        campaign.writej(state_path, initial)
        real_write = campaign.writej
        committed = {}

        def commit_snapshot(message, paths):
            if message.startswith("research(protocol):"):
                snapshot = {str(p.relative_to(self.a)): p.read_bytes()
                            for directory in (self.a / "candidates", self.a / "batches")
                            for p in directory.rglob("*") if p.is_file()}
                if committed:
                    self.assertEqual(snapshot, committed)
                else:
                    committed.update(snapshot)
            return "offline-protocol-commit"

        self.commit.side_effect = commit_snapshot

        def crash_before_state(path, value):
            if Path(path) == state_path:
                self.assertTrue(committed, "Crash must occur after protocol commit")
                raise PowerLoss()
            real_write(path, value)

        dirty_memory = copy.deepcopy(initial)
        with mock.patch.object(campaign, "writej", side_effect=crash_before_state):
            with self.assertRaises(PowerLoss):
                campaign.freeze(dirty_memory, [proposal()])
        self.assertEqual(len(dirty_memory["batches"]), 1)
        self.assertEqual(campaign.readj(state_path), initial)
        pending = campaign.readj(journal)
        self.assertEqual(pending, {"batch": "b0001", "proposals": [proposal()]})
        campaign.STOP.touch()  # Reconcile on startup, then stop before any launch.

        recovered_protocol = None
        for attempt in range(2):
            # Discard all mutated memory, including the successfully reconstructed state.
            real_write(state_path, copy.deepcopy(initial))
            real_write(journal, pending)
            with mock.patch.object(campaign, "native_tick") as native:
                campaign.supervise()
            native.assert_not_called()
            restored = campaign.readj(state_path)
            self.assertFalse(journal.exists())
            self.assertEqual(len(restored["batches"]), 1)
            self.assertEqual(len(restored["candidates"]), 1)
            batch = restored["batches"][0]
            self.assertEqual(batch["id"], "b0001")
            self.assertEqual(batch["protocol_commit"], "offline-protocol-commit")
            self.assertEqual(len({tuple(slot) for slot in batch["schedule"]}), 3)
            protocol = (batch, restored["candidates"])
            if attempt:
                self.assertEqual(protocol, recovered_protocol)
            recovered_protocol = protocol
            for relative, content in committed.items():
                self.assertEqual((self.a / relative).read_bytes(), content)

        # The other crash boundary: state saved, but journal unlink did not happen.
        restored["status"] = "running"
        restored["stop_reason"] = None
        real_write(state_path, restored)
        real_write(journal, pending)
        with mock.patch.object(campaign, "freeze") as freeze:
            campaign.supervise()
        freeze.assert_not_called()
        self.assertFalse(journal.exists())
        self.assertEqual(campaign.readj(state_path)["batches"], restored["batches"])
        campaign.subprocess.Popen.assert_not_called()

    def test_verify_rejects_mutable_schedule_against_git_committed_protocol(self):
        state = state_fixture()
        batch = campaign.freeze(state, [proposal()])
        path = self.a / "batches" / batch["id"] / "protocol.json"
        immutable = path.read_text()
        git = self.patch(campaign, "git", side_effect=lambda *args:
                         campaign.BRANCH if args == ("branch", "--show-current") else immutable)
        original = copy.deepcopy(batch)
        # Still a valid permutation of all slots: structural checks alone cannot catch it.
        batch["schedule"] = list(reversed(batch["schedule"]))
        tampered_disk = json.loads(immutable)
        tampered_disk["schedule"] = batch["schedule"]
        campaign.writej(path, tampered_disk)
        with self.assertRaisesRegex(AssertionError, "Mutable state disagrees"):
            campaign.verify(batch)
        git.assert_any_call("show", original["protocol_commit"] +
                            ":autoresearch/batches/b0001/protocol.json")
        campaign.subprocess.check_output.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith("linux"), "Linux flock semantics")
    def test_native_and_executor_children_keep_inherited_lock_after_parent_close(self):
        # Only this literal program is ever passed to the real Popen.
        dummy = ("import os,sys\n"
                 "os.fstat(int(sys.argv[1]))\n"
                 "print('ready', flush=True)\n"
                 "sys.stdin.read(1)\n")
        for route in ("native", "executor"):
            with self.subTest(route=route):
                lock_path = self.a / (route + ".lock")
                with lock_path.open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fd = lock.fileno()
                    campaign.LOCK_FD = fd

                    def launch_dummy(command, **kwargs):
                        self.assertEqual(kwargs["pass_fds"], (fd,))
                        child = REAL_POPEN([sys.executable, "-I", "-c", dummy, str(fd)],
                                           pass_fds=kwargs["pass_fds"], stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           start_new_session=kwargs["start_new_session"],
                                           cwd=self.root, text=True)
                        try:
                            ready, _, _ = select.select([child.stdout], [], [], 5)
                            self.assertTrue(ready, "Dummy child did not inherit descriptor")
                            self.assertEqual(child.stdout.readline().strip(), "ready")
                            lock.close()  # Simulate supervisor death, without LOCK_UN.
                            with lock_path.open("a") as contender:
                                with self.assertRaises(BlockingIOError):
                                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            _, stderr = child.communicate("x", timeout=5)
                            self.assertEqual(child.returncode, 0, stderr)
                            with lock_path.open("a") as contender:
                                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                fcntl.flock(contender, fcntl.LOCK_UN)
                        finally:
                            if child.poll() is None:
                                child.kill()
                            child.communicate(timeout=5)
                        if route == "native":
                            campaign.writej(self.a / "ticks/t0001/proposal.json",
                                            {"candidates": [proposal()]})
                        return child

                    with mock.patch.object(campaign.subprocess, "Popen", side_effect=launch_dummy) as spawn:
                        if route == "native":
                            (self.a / "director-tick.md").write_text("Offline {{OUTPUT}}")
                            self.assertEqual(campaign.native_tick(state_fixture()), [proposal()])
                        else:
                            measure = types.ModuleType("measure")
                            measure.measure = mock.Mock(return_value={"valid": True})
                            batch = dict(id="b0001", candidates=["dummy"],
                                         schedule=[["dummy", 1]], protocol_commit="offline")
                            with mock.patch.dict(sys.modules, {"measure": measure}), \
                                 mock.patch.object(campaign, "verify"):
                                summary = campaign.batch_execute(batch, fd)
                            self.assertIsNone(summary["stop_reason"])
                            measure.measure.assert_called_once()
                        spawn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
