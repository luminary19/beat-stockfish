"""Offline controller tests; fixtures cannot launch actors, models, Docker, or Git.

Every subprocess entry point fails closed unless replaced by an in-memory fake.
Filesystem fixtures live exclusively beneath /tmp/opencode; measure is a fake
module, never the production evaluator. Run with unittest discovery.
"""
from __future__ import annotations

from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


_SPEC = importlib.util.spec_from_file_location(
    "campaign_under_test", Path(__file__).with_name("campaign.py")
)
campaign = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(campaign)


def proposal(opening=None, asset=None):
    return dict(
        opening=opening or campaign.OPENING.replace("your ability", "your personal ability"),
        asset=asset,
        hypothesis="Neutral wording may affect behavior.",
        prediction="Three complete clean episodes.",
        ablation="Compare the matched neutral wording.",
    )


def state_fixture():
    return dict(
        status="initialized", stop_reason=None, historical_fingerprints={},
        candidates={}, batches=[], image_id="fake-image-never-inspected",
    )


def batch_fixture():
    return dict(
        id="b0001", candidates=["candidate-a", "candidate-b"],
        schedule=[[cid, rep] for rep in range(1, 4)
                  for cid in ("candidate-a", "candidate-b")],
        protocol_commit="fake-commit", status="preregistered",
    )


class OfflineCase(unittest.TestCase):
    def setUp(self):
        parent = Path("/tmp/opencode")
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="campaign-test-", dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.a = self.root / "autoresearch"
        self.logs = self.root / "logs"
        self.a.mkdir()
        for name, value in dict(ROOT=self.root, A=self.a, LOGS=self.logs,
                                 STOP=self.a / "STOP", LOCK_FD=None, NATIVE_CHILD=None).items():
            self.patch(campaign, name, value)
        # Never fall through to a real process, signal, Git call, or image read.
        for name in ("Popen", "run", "check_output", "call", "check_call"):
            self.patch(campaign.subprocess, name, side_effect=AssertionError(
                "Real subprocesses are forbidden in campaign tests"))
        self.patch(campaign, "git", side_effect=AssertionError("Real Git is forbidden"))
        self.patch(campaign, "base_prompt", side_effect=AssertionError("No Docker"))
        self.patch(campaign.os, "killpg", side_effect=AssertionError("No real signals"))
        self.patch(campaign.signal, "signal")
        self.patch(campaign, "event")
        self.commit = self.patch(campaign, "commit", return_value="fake-commit")

    def patch(self, target, name, *args, **kwargs):
        patcher = mock.patch.object(target, name, *args, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result


class ContentTests(OfflineCase):
    def test_costs_separate_rendered_label_target_and_asset_title(self):
        base = campaign.OPENING
        prompt = base.replace("your ability", "[your own ability](definition.md)")
        asset = "# Ability Definition\nPersonal skill."
        result = campaign.costs(base, prompt, asset)
        self.assertEqual(campaign.rendered(prompt), base.replace("your ability", "your own ability"))
        self.assertEqual(result["added_prompt_words"], 1)
        self.assertEqual(result["deleted_or_replaced_prompt_words"], 0)
        self.assertEqual(result["word_edit_distance"], 1)
        self.assertEqual(result["file_words"], 4)  # Includes both title words.
        self.assertEqual(result["file_bytes"], len(asset.encode()))
        self.assertEqual(result["link_targets"], ["definition.md"])
        self.assertEqual(result["link_target_words"], 2)
        self.assertEqual(result["link_markup_bytes"], len("[](definition.md)"))
        self.assertEqual(result["visible_and_file_non_original_words"], 5)
        self.assertEqual(result["total_non_original_lexical_content"], 7)
        self.assertEqual(result["net_prompt_words"], 1)
        self.assertEqual(result["net_prompt_plus_file_words"], 5)
        self.assertIn("definition.md", result["exact_prompt_diff"])

    def test_replacements_count_as_additions_and_deletions(self):
        result = campaign.costs("your ability", "your skill", None)
        self.assertEqual(result["added_prompt_words"], 1)
        self.assertEqual(result["deleted_or_replaced_prompt_words"], 1)
        self.assertEqual(result["word_edit_distance"], 1)
        self.assertEqual(result["net_prompt_words"], 0)

    def test_absent_and_empty_assets_have_distinct_fingerprints(self):
        prompt = campaign.OPENING
        absent = campaign.fingerprint(prompt, None)
        empty = campaign.fingerprint(prompt, "")
        self.assertNotEqual(absent, empty)
        self.assertEqual(absent, campaign.fingerprint(prompt, None))
        self.assertEqual(empty, campaign.fingerprint(prompt, ""))
        self.assertNotEqual(empty, campaign.fingerprint(prompt, " "))
        for asset, label in ((None, "absent"), ("", "empty")):
            with self.subTest(asset=asset):
                result = campaign.costs(prompt, prompt, asset)
                self.assertEqual(result["asset_state"], label)
                self.assertEqual(result["file_words"], 0)
                self.assertEqual(result["file_bytes"], 0)

    def test_validate_accepts_neutral_link_and_title(self):
        opening = campaign.OPENING.replace("ability", "[ability](definition.md)")
        p = proposal(opening, "# Ability\nPersonal skill.")
        self.assertEqual(campaign.validate_proposal(p), (opening, p["asset"]))
        for asset in (None, ""):
            self.assertEqual(campaign.validate_proposal(proposal(asset=asset))[1], asset)

    def test_validate_rejects_prohibited_vocabulary_in_opening_and_asset(self):
        for banned in ("stockfish", "engine", "search", "tools", "python", "ignore", "instructions"):
            for location in ("opening", "asset"):
                with self.subTest(banned=banned, location=location):
                    p = proposal()
                    p[location] = (p["opening"][:-1] + " " + banned + "."
                                   if location == "opening" else banned)
                    with self.assertRaises(AssertionError):
                        campaign.validate_proposal(p)

    def test_validate_rejects_bad_links(self):
        for target in ("https://example.com/definition.md", "/workdir/definition.md",
                       "../definition.md", "other.md", "definition.md#ability",
                       'definition.md "ability"', ""):
            with self.subTest(target=target):
                opening = campaign.OPENING.replace("ability", f"[ability]({target})")
                with self.assertRaises(AssertionError):
                    campaign.validate_proposal(proposal(opening))

    def test_validate_requires_preregistration_fields(self):
        for field in ("hypothesis", "prediction", "ablation"):
            with self.subTest(field=field):
                p = proposal()
                del p[field]
                with self.assertRaises(AssertionError):
                    campaign.validate_proposal(p)

    def test_historical_own_only_duplicate_refused_before_writes(self):
        base = campaign.OPENING + "\nUnchanged task body.\n"
        (self.a / "original-task.txt").write_text(base)
        state = state_fixture()
        with mock.patch.object(campaign, "readj", return_value={}) as manifests:
            state["historical_fingerprints"] = campaign.historical(base)
        self.assertEqual(manifests.call_count, 3)
        own = campaign.OPENING.replace("your ability", "your own ability")
        self.assertIn(campaign.fingerprint(base.replace(campaign.OPENING, own), None),
                      state["historical_fingerprints"])
        original = copy.deepcopy(state)
        with mock.patch.object(campaign, "writej") as write:
            # A valid first item must not be partially frozen before item two fails.
            with self.assertRaisesRegex(AssertionError, "Duplicate"):
                campaign.freeze(state, [proposal(), proposal(own)])
        write.assert_not_called()
        self.commit.assert_not_called()
        self.assertFalse((self.a / "candidates").exists())
        self.assertEqual(state, original)

    def test_freeze_allocates_exactly_three_unique_slots_per_candidate(self):
        (self.a / "original-task.txt").write_text(campaign.OPENING)
        self.patch(campaign, "frozen_files", return_value=[])
        state = state_fixture()
        for count in (1, 2):
            with self.subTest(candidate_count=count):
                # Distinct fingerprints across subtests, including absent/empty files.
                proposals = [proposal(asset=None if count == 1 else "")]
                if count == 2:
                    proposals.append(proposal(campaign.OPENING.replace("ability", "skill"), ""))
                batch = campaign.freeze(state, proposals)
                self.assertEqual(len(batch["schedule"]), count * 3)
                self.assertEqual(len({tuple(slot) for slot in batch["schedule"]}), count * 3)
                self.assertEqual(Counter(cid for cid, _ in batch["schedule"]),
                                 Counter({cid: 3 for cid in batch["candidates"]}))
                for cid in batch["candidates"]:
                    self.assertEqual(sorted(rep for c, rep in batch["schedule"] if c == cid), [1, 2, 3])
                persisted = campaign.readj(self.a / "research-state.json")
                self.assertEqual(persisted, state)
                self.assertEqual(batch["protocol_commit"], "fake-commit")


class PersistenceAndErrorTests(OfflineCase):
    def test_state_write_flushes_and_atomically_replaces_complete_json(self):
        path = self.a / "research-state.json"
        campaign.writej(path, {"old": True})
        replacement = {"status": "running", "unicode": "棋", "batches": [1, 2, 3]}
        real_replace = campaign.os.replace
        with mock.patch.object(campaign.os, "fsync", wraps=campaign.os.fsync) as sync:
            def replace(source, destination):
                self.assertEqual(Path(destination), path)
                self.assertEqual(Path(source), path.with_name(path.name + ".tmp"))
                self.assertEqual(campaign.readj(path), {"old": True})
                self.assertEqual(campaign.readj(source), replacement)
                sync.assert_called_once()
                real_replace(source, destination)

            with mock.patch.object(campaign.os, "replace", side_effect=replace) as atomic:
                campaign.writej(path, replacement)
            atomic.assert_called_once()
        self.assertEqual(campaign.readj(path), replacement)
        self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_failed_replace_preserves_previous_durable_state(self):
        path = self.a / "research-state.json"
        campaign.writej(path, {"old": True})
        with mock.patch.object(campaign.os, "replace", side_effect=OSError("simulated failure")):
            with self.assertRaisesRegex(OSError, "simulated failure"):
                campaign.writej(path, {"new": True})
        self.assertEqual(campaign.readj(path), {"old": True})

    def test_actual_error_classification_and_generic_429(self):
        for error, expected in (
            (None, None), ({}, None),
            ({"code": "insufficient_quota", "status": 429}, "quota_exhausted"),
            ({"message": "Usage limit has been reached"}, "quota_exhausted"),
            ({"type": "AuthenticationError"}, "blocker_auth_config"),
            ({"code": "model_not_found"}, "blocker_auth_config"),
            ({"status": 429, "message": "Too many requests"}, "blocker_infrastructure"),
            ({"type": "RateLimitError", "status": 429}, "blocker_infrastructure"),
            ({"message": "Connection reset"}, "blocker_infrastructure"),
        ):
            with self.subTest(error=error):
                self.assertEqual(campaign.classify(error), expected)

    def test_native_tick_classifies_only_typed_error_events(self):
        (self.a / "director-tick.md").write_text("Offline fixture output: {{OUTPUT}}")
        for index, error in enumerate((None, {"code": "insufficient_quota"},
                                       {"status": 429, "message": "Too many requests"})):
            with self.subTest(error=error):
                state = state_fixture()
                state["batches"] = [{} for _ in range(index)]
                directory = self.a / "ticks" / f"t{index + 1:04d}"
                candidates = [proposal()]

                def fake_director(*args, **kwargs):
                    # Only write fixture JSON; no agent, command, or actor is run.
                    events = [
                        {"type": "text", "text": "insufficient_quota invalid_api_key"},
                        {"type": "tool", "error": {"code": "insufficient_quota"}},
                        {"type": "error", "error": "insufficient_quota"},
                    ]
                    if error is not None:
                        events.append({"type": "error", "error": error})
                    kwargs["stdout"].write(("\n".join(map(json.dumps, events)) + "\n").encode())
                    campaign.writej(directory / "proposal.json", {"candidates": candidates})
                    return mock.Mock(pid=999999,wait=mock.Mock(return_value=0))

                with mock.patch.object(campaign.subprocess, "Popen", side_effect=fake_director), \
                     mock.patch.object(campaign, "classify", wraps=campaign.classify) as classify:
                    result = campaign.native_tick(state)
                if error is None:
                    self.assertEqual(result, candidates)
                    classify.assert_not_called()
                    self.assertIsNone(state["stop_reason"])
                else:
                    self.assertIsNone(result)
                    classify.assert_called_once_with(error)
                    expected = "quota_exhausted" if index == 1 else "blocker_infrastructure"
                    self.assertEqual(state["stop_reason"], expected)


class ExecutorTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.patch(campaign, "verify")
        self.clock = 0
        self.actors = []
        self.launches = []
        self.peak = 0
        self.measure = mock.Mock(side_effect=lambda *args: {
            "valid": True, "completed": True, "clean_complete": True, "error_class": None,
        })
        module = types.ModuleType("measure")
        module.measure = self.measure
        patcher = mock.patch.dict(sys.modules, {"measure": module})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.patch(campaign.time, "sleep", side_effect=self.advance)
        self.popen = self.patch(campaign.subprocess, "Popen", side_effect=self.fake_actor)

    def advance(self, seconds):
        self.clock += seconds
        if self.clock > 30:
            self.fail("Executor failed to make progress with finite fake actors")

    def fake_actor(self, command, **kwargs):
        # This deliberately is not an actor wrapper: it only advances fake time.
        case = self

        class FakeActor:
            def __init__(self):
                self.pid = 900000 + len(case.actors)
                self.deadline = case.clock + 2

            def poll(self):
                return 0 if case.clock >= self.deadline else None

        actor = FakeActor()
        self.actors.append(actor)
        self.launches.append((command, kwargs, self.clock))
        self.peak = max(self.peak, sum(p.poll() is None for p in self.actors))
        self.assertLessEqual(self.peak, 4)
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["pass_fds"], (123,))
        directory = Path(command[command.index("--log-dir") + 1])
        self.assertTrue((directory / "started.json").exists())
        self.assertEqual(kwargs["env"]["CAMPAIGN_TRANSPORT_ERRORS"],
                         str(directory / "transport-errors.jsonl"))
        return actor

    def test_executor_runs_all_six_slots_with_at_most_four_live_actors(self):
        batch = batch_fixture()
        summary = campaign.batch_execute(batch, 123)
        self.assertEqual(self.peak, 4)
        self.assertEqual(self.popen.call_count, 6)
        self.assertEqual(self.measure.call_count, 6)
        self.assertEqual([launch[2] for launch in self.launches], [0, 0, 0, 0, 2, 2])
        self.assertEqual(summary["unscheduled"], [])
        self.assertIsNone(summary["stop_reason"])
        for cid, rep in batch["schedule"]:
            result = campaign.readj(self.logs / cid / f"run-{rep:02d}" / "result.json")
            self.assertEqual((result["candidate"], result["replicate"]), (cid, rep))
            self.assertTrue(result["clean_complete"])
        for _, kwargs, _ in self.launches:
            self.assertTrue(kwargs["stdout"].closed)

    def test_restart_skips_completed_slots_and_does_not_remeasure_them(self):
        batch = batch_fixture()
        for cid, rep in batch["schedule"][:2]:
            directory = self.logs / cid / f"run-{rep:02d}"
            campaign.writej(directory / "started.json", {"previous": True})
            campaign.writej(directory / "result.json", {"valid": True, "sentinel": cid})
        campaign.batch_execute(batch, 123)
        self.assertEqual(self.popen.call_count, 4)
        self.assertEqual(self.measure.call_count, 4)
        for cid, rep in batch["schedule"][:2]:
            self.assertEqual(campaign.readj(self.logs / cid / f"run-{rep:02d}" / "result.json"),
                             {"valid": True, "sentinel": cid})
        self.popen.reset_mock()
        self.measure.reset_mock()
        campaign.batch_execute(batch, 123)
        self.popen.assert_not_called()
        self.measure.assert_not_called()

    def test_restart_refuses_started_slot_without_result_before_any_launch(self):
        batch = batch_fixture()
        cid, rep = batch["schedule"][-1]
        directory = self.logs / cid / f"run-{rep:02d}"
        campaign.writej(directory / "started.json", {"previous": True})
        with self.assertRaisesRegex(RuntimeError, "manual reconciliation.*never replay"):
            campaign.batch_execute(batch, 123)
        self.popen.assert_not_called()
        self.measure.assert_not_called()
        self.assertFalse((directory / "result.json").exists())


class SupervisorTests(OfflineCase):
    def test_supervisor_continues_through_three_batches_until_typed_stop(self):
        state = state_fixture()
        snapshots = []
        self.patch(campaign, "readj", return_value=state)
        self.patch(campaign, "writej", side_effect=lambda path, value: snapshots.append(copy.deepcopy(value)))
        report = self.patch(campaign, "report")

        def tick(current):
            self.assertIs(current, state)
            if len(current["batches"]) == 3:
                current["status"] = current["stop_reason"] = "quota_exhausted"
                return None
            if len(current["batches"]) > 3:
                raise AssertionError("Supervisor continued beyond fake stop")
            return [proposal(asset="skill " * (len(current["batches"]) + 1))]

        def freeze(current, proposals):
            self.assertEqual(len(proposals), 1)
            batch = dict(id=f"b{len(current['batches']) + 1:04d}", status="preregistered")
            current["batches"].append(batch)
            return batch

        def ingest(current, batch):
            self.assertEqual(batch["status"], "running")
            batch["status"] = "completed"
            current["status"] = "running"
            current["stop_reason"] = None

        children = []

        def executor(command, **kwargs):
            # Never invokes campaign.py or its actors; the child is entirely fake.
            child = mock.Mock(wait=mock.Mock(return_value=0))
            children.append(child)
            self.assertEqual(command[1:3], [str(self.a / "campaign.py"), "batch"])
            self.assertEqual(command[-2:], ["--id", f"b{len(children):04d}"])
            self.assertEqual(kwargs["env"]["CAMPAIGN_LOCK_FD"], str(kwargs["pass_fds"][0]))
            return child

        native = self.patch(campaign, "native_tick", side_effect=tick)
        frozen = self.patch(campaign, "freeze", side_effect=freeze)
        ingested = self.patch(campaign, "ingest", side_effect=ingest)
        popen = self.patch(campaign.subprocess, "Popen", side_effect=executor)
        campaign.supervise()
        self.assertEqual(native.call_count, 4)
        self.assertEqual(frozen.call_count, 3)
        self.assertEqual(ingested.call_count, 3)
        self.assertEqual(popen.call_count, 3)
        self.assertEqual([b["status"] for b in state["batches"]], ["completed"] * 3)
        self.assertEqual(state["status"], "quota_exhausted")
        self.assertEqual([s for s in snapshots if 'batches' in s][-1], state)
        self.assertEqual(snapshots[-1]['reason'], 'quota_exhausted')
        self.assertEqual(report.call_count, 4)
        for child in children:
            child.wait.assert_called_once_with()
        self.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
