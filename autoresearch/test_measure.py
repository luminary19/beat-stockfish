"""Offline measurement regressions: no Docker, actor, or model requests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure as measurement
from campaign import DEST, digest


class MeasureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.candidate = self.root / 'candidate'
        self.candidate.mkdir()
        self.episode = self.root / 'episode'
        self.episode.mkdir()
        self.prompt = 'Exact user prompt.\n'
        self.candidate.joinpath('prompt.txt').write_text(self.prompt)
        self.protocol = dict(prompt_sha256=digest(self.prompt.encode()), asset_sha256=None)
        self.save_protocol()
        self.path = self.episode / 'test.eval'
        self.path.write_bytes(b'raw eval bytes')
        self.info = NS(name=self.path.as_uri())
        self.metadata = dict(findings=[], task_score=1.0, engine_contacted=False, result='loss')
        self.sample = NS(id='v001', epoch=1, uuid='sample-uuid', error=None,
            error_retries=None, invalidation=None, store={'debrief': {'text': 'Done.'}},
            scores={'fresh_grader': NS(value=1.0, metadata=self.metadata)},
            messages=[NS(role='user', content=self.prompt),
                NS(role='assistant', content='', tool_calls=[NS(id='call-1',
                    function='capped_bash', arguments={'cmd': 'cat definition.md'}, parse_error=None)]),
                NS(role='tool', content='', tool_call_id='call-1', error=None),
                NS(role='system', content='Debrief prompt'),
                NS(role='assistant', content='Done.', tool_calls=None)])
        self.log = NS(status='success', error=None, invalidated=False, samples=[self.sample])

    def save_protocol(self):
        self.candidate.joinpath('protocol.json').write_text(json.dumps(self.protocol))

    def asset(self, content):
        self.candidate.joinpath('definition.md').write_bytes(content)
        self.protocol['asset_sha256'] = digest(content)
        self.save_protocol()
        self.sample.store['task_assets'] = {DEST: {'sha256': digest(content)}}

    def run_measure(self, rc=0, infos=None):
        with patch.object(measurement, 'list_eval_logs', return_value=[self.info] if infos is None else infos), \
             patch.object(measurement, 'read_eval_log', return_value=self.log):
            return measurement.measure(self.episode, self.candidate, rc)

    def test_success_trace_hash_and_empty_read_caveat(self):
        self.asset(b'')
        result = self.run_measure()
        self.assertTrue(result['clean_complete'])
        self.assertEqual(result['asset_state'], 'empty')
        self.assertTrue(result['reads'][0]['read_attempt'])
        self.assertFalse(result['reads'][0]['content_read_proven'])
        trace_bytes = Path(result['trace_path']).read_bytes()
        self.assertEqual(digest(trace_bytes), result['trace_sha256'])
        trace = json.loads(trace_bytes)
        self.assertEqual([e['kind'] for e in trace['entries']], ['tool_call', 'tool_response'])
        self.assertEqual(trace['entries'][1]['message']['content'], '')
        self.assertEqual(trace['entries'][0]['coordinates']['sample_id'], 'v001')
        self.assertEqual(result['eval_hashes'][self.info.name], digest(b'raw eval bytes'))

    def test_partial_game_is_valid_not_infrastructure(self):
        self.metadata.update(task_score=0.0, result=None, findings=['the game was not completed'])
        result = self.run_measure()
        self.assertTrue(result['valid'])
        self.assertFalse(result['clean_complete'])
        self.assertFalse(result['completed'])
        self.assertIsNone(result['error_class'])

    def test_exact_search_finding_not_contact_or_substring(self):
        self.metadata.update(engine_contacted=True, findings=['not a supplied engine service was used'])
        self.assertFalse(self.run_measure()['engine_used'])
        self.metadata['findings'] = [measurement.ENGINE_FINDING]
        result = self.run_measure()
        self.assertTrue(result['engine_used'])
        self.assertTrue(result['valid'])
        self.assertFalse(result['clean_complete'])

    def test_malformed_grades_never_succeed(self):
        baseline = copy.deepcopy(self.metadata)
        for patch_values in ({'findings': 'none'}, {'findings': [1]}, {'task_score': True},
                             {'task_score': '1'}, {'task_score': 0.5},
                             {'engine_contacted': 0}, {'result': 'unfinished'},
                             {'result': None}, {'grade_error': ''}):
            with self.subTest(values=patch_values):
                self.metadata.clear()
                self.metadata.update(baseline, **patch_values)
                result = self.run_measure()
                self.assertFalse(result['grade_valid'])
                self.assertFalse(result['clean_complete'])
                self.assertEqual(result['error_class'], 'blocker_infrastructure')
        self.metadata.clear()
        self.metadata.update(baseline)
        del self.metadata['result']
        self.assertFalse(self.run_measure()['grade_valid'])

    def test_named_fresh_grader_required(self):
        self.sample.scores['other_grader'] = self.sample.scores.pop('fresh_grader')
        self.assertFalse(self.run_measure()['grade_valid'])

    def test_initial_prompt_exact_and_no_operator_message(self):
        self.sample.messages[0].content = self.prompt.rstrip()
        self.assertFalse(self.run_measure()['prompt_matches'])
        self.sample.messages[0].content = self.prompt
        for role in ('system', 'developer', 'user'):
            self.sample.messages.insert(0, NS(role=role, content='Extra input'))
            self.assertFalse(self.run_measure()['prompt_matches'])
            self.sample.messages.pop(0)
        self.assertTrue(self.run_measure()['prompt_matches'])

    def test_absence_is_distinct_from_empty(self):
        self.assertTrue(self.run_measure()['assets_match'])
        self.sample.store['task_assets'] = {DEST: {'sha256': digest(b'')}}
        self.assertFalse(self.run_measure()['assets_match'])
        self.asset(b'')
        self.assertTrue(self.run_measure()['assets_match'])
        del self.sample.store['task_assets']
        self.assertFalse(self.run_measure()['assets_match'])

    def test_asset_bytes_checked_when_available(self):
        self.asset(b'hello')
        record = self.sample.store['task_assets'][DEST]
        record.update(bytes=5, content='hello')
        self.assertTrue(self.run_measure()['assets_match'])
        record['content'] = 'wrong'
        self.assertFalse(self.run_measure()['assets_match'])
        record['content'] = 'hello'
        record['bytes'] = 0
        self.assertFalse(self.run_measure()['assets_match'])

    def test_source_tampering_invalidates(self):
        self.candidate.joinpath('prompt.txt').write_text('changed')
        self.assertFalse(self.run_measure()['valid'])

    def test_missing_duplicate_logs_and_samples(self):
        for infos in ([], [self.info, self.info]):
            result = self.run_measure(infos=infos)
            self.assertFalse(result['valid'])
            self.assertEqual(result['error_class'], 'blocker_infrastructure')
        self.log.samples = [self.sample, self.sample]
        self.assertFalse(self.run_measure()['valid'])
        self.log.samples = []
        self.assertFalse(self.run_measure()['valid'])

    def test_nonzero_rc_and_terminal_status(self):
        self.assertFalse(self.run_measure(rc=1)['valid'])
        self.log.status = 'cancelled'
        self.assertFalse(self.run_measure()['valid'])

    def test_transcript_is_never_classified(self):
        self.sample.messages[2].content = 'insufficient_quota invalid_api_key'
        with patch.object(measurement, 'classify', side_effect=AssertionError('classified transcript')):
            self.assertTrue(self.run_measure()['clean_complete'])

    def test_transient_transport_retained_but_not_terminal(self):
        original = {'type': 'RateLimitError', 'status_code': 429, 'message': 'retry later'}
        self.episode.joinpath('transport-errors.jsonl').write_text(json.dumps(original) + '\n')
        result = self.run_measure()
        self.assertTrue(result['clean_complete'])
        self.assertIsNone(result['error_class'])
        self.assertEqual(result['errors'][0]['error'], original)
        self.assertEqual(result['errors'][0]['coordinates']['line'], 1)

    def test_permanent_transport_invalidates_even_with_grade(self):
        for code, expected in (('insufficient_quota', 'quota_exhausted'),
                               ('invalid_api_key', 'blocker_auth_config')):
            self.episode.joinpath('transport-errors.jsonl').write_text(json.dumps({'code': code}))
            result = self.run_measure()
            self.assertEqual(result['error_class'], expected)
            self.assertFalse(result['valid'])

    def test_errors_preserve_full_objects_and_coordinates(self):
        original = dict(message='terminal failure', traceback='full traceback', extra={'code': 500})
        self.log.error = NS(**original)
        self.sample.error = NS(**original)
        self.sample.store['debrief'] = {'error': original}
        result = self.run_measure()
        self.assertFalse(result['valid'])
        for source in ('eval', 'sample', 'debrief'):
            error = next(e for e in result['errors'] if e['source'] == source)
            self.assertEqual(error['error'], original)
            self.assertEqual(error['coordinates']['eval_path'], self.info.name)
        self.assertEqual(result['errors'][2]['coordinates']['store_key'], 'debrief.error')

    def test_retry_evidence_invalidates_and_heuristics_not_audit(self):
        self.sample.error_retries = [NS(message='retry', traceback='full')]
        self.sample.messages[1].tool_calls[0].arguments['cmd'] = 'python3 -c "board.legal_moves; minimax()"'
        result = self.run_measure()
        self.assertFalse(result['valid'])
        flags = result['alternate_computation_flags']
        self.assertTrue(flags['legal_move_enumeration'])
        self.assertTrue(flags['alternate_evaluator'])
        self.assertFalse(flags['full_audit'])


if __name__ == '__main__':
    unittest.main()
