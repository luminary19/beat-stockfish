#!/usr/bin/env python3
"""User-authorized timed exploration -> independent 5 x 10 confirmation.

Reuses the frozen actor and offline measurement. Does not modify live legacy
runner code, replay started slots, or combine pilot and confirmation outcomes.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

import campaign as c

A = c.A
REQUEST = A / 'phase-request.json'
STATE = A / 'phase-state.json'
CONF = A / 'confirmation'
CONF_LOGS = c.ROOT / 'logs/minimal-prompt-confirmation'
HANDOFF = 'phase-handoff-20261108-r1'
CHILD = None
PERMANENT = {'quota_exhausted', 'blocker_auth_config'}


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


def expired(request, clock=None):
    return (time.time() if clock is None else clock) >= timestamp(request['exploration_deadline'])


def priority(request):
    return dict(opening=request['priority_opening'], asset=None,
        hypothesis='User-directed transfer test: inline your own reasoning can yield 3/3 valid completed games without supplied-engine searches.',
        prediction='Three valid clean completions; any supplied-engine search refutes the perfect-cohort prediction. Missing and partial games never support it.',
        ablation='Replace ability with own reasoning in the original opening. No link or asset. Compared with cd6bc3ff4740d this relocates content and removes retrieval, so multiple factors change. Two added lexical words, one deleted word, one net additional word.',
        parent='user steering 2026-11-08; cd6bc3ff4740d', direction='BROADEN')


def eligible(candidate):
    outcomes = candidate.get('outcomes', [])
    return len(outcomes) == 3 and all(o.get('valid') is True and o.get('completed') is True for o in outcomes)


def ranking(candidate):
    return (-sum(o.get('clean_complete') is True for o in candidate['outcomes']),
            candidate['costs']['total_non_original_lexical_content'],
            candidate['costs']['word_edit_distance'], candidate['id'])


def select(state, request):
    """Fixed, outcome-blind-to-confirmation policy, specified before selection."""
    pool = sorted((v for v in state['candidates'].values()
                   if eligible(v) and v['proposal']['opening'] != request['excluded_opening']), key=ranking)
    chosen, reasons, fingerprints = [], {}, set()

    def take(predicate, reason):
        for v in pool:
            if v['fingerprint'] not in fingerprints and predicate(v):
                chosen.append(v)
                fingerprints.add(v['fingerprint'])
                reasons[v['id']] = reason
                return

    take(lambda v: v['proposal']['opening'] == request['priority_opening'] and v['proposal']['asset'] is None,
         'User-priority direct inline transfer test, retained even if its pilot is negative.')
    for term, reason in [('reasoning', 'Shortest/highest-performing linked reasoning package.'),
                         ('knowledge', 'Faculty-transfer comparison: linked knowledge package.'),
                         ('means', 'Explicit definitional reference to compare with short fragments.')]:
        take(lambda v, term=term: '[your ability](definition.md)' in v['proposal']['opening']
             and term in c.words((v['proposal']['asset'] or '').lower()), reason)
    while len(chosen) < request['confirmation_candidates']:
        before = len(chosen)
        take(lambda v: True, 'Best remaining pilot by clean count, lexical cost, edit distance, ID.')
        if len(chosen) == before:
            raise RuntimeError('Fewer than five eligible distinct fully measured pilot packages')
    return chosen, reasons


def wilson(success, total):
    if not total:
        return None
    z = 1.959963984540054
    p = success / total
    center = (p + z*z/(2*total))/(1 + z*z/total)
    half = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/(1 + z*z/total)
    return [max(0, center-half), min(1, center+half)]


def phase_publish(phase):
    c.writej(STATE, phase)
    header = ('# Timed search and confirmation\n\n'
              f"Phase: **{phase['phase']}**\n\n"
              f"Exploration cutoff (UTC): {phase['exploration_deadline']}\n\n"
              'Confirmation: five fixed prompt packages, ten NEW games each; pilot results stay separate.\n\n')
    text = header
    if (CONF/'results.md').exists():
        text += (CONF/'results.md').read_text()
    else:
        text += 'Pilot leaderboard: `autoresearch/leaderboard.md`.\n'
    text += '\nStop reason: ' + str(phase.get('stop_reason')) + '\n'
    (A/'to_human/PHASED.md').write_text(text)
    (A/'to_human/LATEST.md').write_text(text)


def confirmation_report(plan):
    rows = []
    for cid in plan['candidates']:
        outcomes = [c.readj(CONF_LOGS/cid/f'run-{rep:02d}'/'result.json')
                    for rep in range(1, 11) if (CONF_LOGS/cid/f'run-{rep:02d}'/'result.json').exists()]
        clean = sum(o.get('clean_complete') is True for o in outcomes)
        valid = sum(o.get('valid') is True and o.get('completed') is True for o in outcomes)
        rows.append(dict(candidate=cid, recorded=len(outcomes), valid_complete=valid,
            clean_complete=clean, engine_use=sum(o.get('engine_used') is True for o in outcomes),
            invalid_or_partial=len(outcomes)-valid, missing=10-len(outcomes),
            completed_clean_wilson95=wilson(clean, valid),
            outcomes=outcomes, selection_reason=plan['selection_reasons'][cid]))
    c.writej(CONF/'results.json', rows)
    text = '## Fresh confirmation results\n\n'
    text += '| Candidate | Clean / 10 assigned | Engine use | Valid complete | Invalid/partial | Missing |\n|---|---:|---:|---:|---:|---:|\n'
    for r in rows:
        text += f"| {r['candidate']} | {r['clean_complete']}/10 | {r['engine_use']} | {r['valid_complete']} | {r['invalid_or_partial']} | {r['missing']} |\n"
    text += ('\nNo pooling with pilots. Missing/partial/error outcomes are not successes. '
             'Supplied-engine non-use does not establish unaided play; full traces and computation flags are retained. '
             'Wilson intervals in results.json describe valid completed confirmation games only, '
             'and do not adjust for selecting prompts on pilot outcomes.\n')
    (CONF/'results.md').write_text(text)


def confirmation_freeze(state, request):
    chosen, reasons = select(state, request)
    CONF.mkdir(exist_ok=True)
    if (CONF/'protocol.json').exists():
        raise RuntimeError('Existing confirmation protocol needs reconciliation, never reselect or replay')
    paths = []
    for source in chosen:
        cid = source['id']
        src, dst = A/'candidates'/cid, CONF/'candidates'/cid
        dst.mkdir(parents=True)
        for name in ('prompt.txt', 'definition.md'):
            if (src/name).exists():
                (dst/name).write_bytes((src/name).read_bytes())
        prompt = (dst/'prompt.txt').read_text()
        asset = (dst/'definition.md').read_text() if (dst/'definition.md').exists() else None
        assert c.fingerprint(prompt, asset) == source['fingerprint']
        meta = dict(id=cid, fingerprint=source['fingerprint'],
            prompt_sha256=c.digest(prompt.encode()),
            asset_sha256=None if asset is None else c.digest(asset.encode()),
            proposal=source['proposal'], costs=source['costs'],
            config={**c.CONFIG, 'replicates': 10}, phase='confirmation',
            pilot_protocol=str(src/'protocol.json'), pilot_outcomes=source['outcomes'],
            pilot_trace_audit=source.get('trace_audit'), selection_reason=reasons[cid],
            created=c.now(), metric='Valid completed game without supplied-engine searches; 10 assigned episodes; missing/partial never clean')
        c.writej(dst/'protocol.json', meta)
        paths.append(dst)
    rng = random.Random(2026110801)
    schedule = []
    ids = [v['id'] for v in chosen]
    for rep in range(1, 11):
        order = ids.copy()
        rng.shuffle(order)
        schedule.extend([[cid, rep] for cid in order])
    plan = dict(phase='confirmation', created=c.now(), candidates=ids, schedule=schedule,
        config={**c.CONFIG, 'replicates': 10}, image_id=state['image_id'],
        allocation_seed=2026110801, model_seed=None, selection_reasons=reasons,
        selection_policy=request['selection_policy'],
        pilot_state_sha256=c.digest((A/'research-state.json').read_bytes()),
        code_hashes={str(f.relative_to(c.ROOT)): c.digest(f.read_bytes())
                     for f in [*c.frozen_files(), Path(__file__), REQUEST]})
    c.writej(CONF/'protocol.json', plan)
    paths.append(CONF/'protocol.json')
    sha = c.commit('research(protocol): five selected prompts x ten fresh confirmation games', paths)
    c.writej(CONF/'registration.json', dict(protocol_commit=sha, time=c.now()))
    c.event('confirmation_preregistered', candidates=ids, commit=sha, episodes=50)
    return plan


def verify_confirmation(plan):
    sha = c.readj(CONF/'registration.json')['protocol_commit']
    assert c.git('branch', '--show-current') == c.BRANCH
    assert json.loads(c.git('show', sha+':autoresearch/confirmation/protocol.json')) == plan
    assert plan['config'] == {**c.CONFIG, 'replicates': 10}
    ids = plan['candidates']
    expected = {(cid, rep) for cid in ids for rep in range(1, 11)}
    actual = [tuple(s) for s in plan['schedule']]
    assert len(ids) == len(set(ids)) == 5 and len(actual) == len(expected) == 50 and set(actual) == expected
    for name, digest in plan['code_hashes'].items():
        assert c.digest((c.ROOT/name).read_bytes()) == digest, 'Frozen confirmation code changed: '+name
    image = subprocess.check_output(['docker','image','inspect',c.CONFIG['image'],'--format','{{.Id}}'], text=True).strip()
    assert image == plan['image_id']
    for cid in ids:
        directory = CONF/'candidates'/cid
        for path in directory.iterdir():
            assert subprocess.check_output(['git','show',sha+':'+str(path.relative_to(c.ROOT))], cwd=c.ROOT) == path.read_bytes()


def confirmation_command(cid, rep):
    cmd = c.command(cid, rep)
    cmd[cmd.index('--task-prompt-file')+1] = str(CONF/'candidates'/cid/'prompt.txt')
    cmd[cmd.index('--log-dir')+1] = str(CONF_LOGS/cid/f'run-{rep:02d}')
    if '--task-file' in cmd:
        cmd[cmd.index('--task-file')+1] = str(CONF/'candidates'/cid/'definition.md')
    return cmd


def permanent_errors(directory):
    path = directory/'transport-errors.jsonl'
    kinds = set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                kind = c.classify(json.loads(line))
            except json.JSONDecodeError:
                continue
            if kind in PERMANENT:
                kinds.add(kind)
    return 'quota_exhausted' if 'quota_exhausted' in kinds else 'blocker_auth_config' if kinds else None


def stop_groups(active, elapsed, sent):
    sig = signal.SIGKILL if elapsed > 60 else signal.SIGTERM if elapsed > 30 else signal.SIGINT
    for proc, *_ in active.values():
        if proc.poll() is None and (proc.pid, sig) not in sent:
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass
            sent.add((proc.pid, sig))


def confirmation_execute(lock_fd):
    from measure import measure
    plan = c.readj(CONF/'protocol.json')
    verify_confirmation(plan)
    pending, active, sent = [], {}, set()
    reason, terminating = None, None
    for cid, rep in plan['schedule']:
        d = CONF_LOGS/cid/f'run-{rep:02d}'
        if (d/'result.json').exists():
            r = c.readj(d/'result.json')
            if r.get('error_class'):
                reason = r['error_class']
        elif (d/'started.json').exists():
            raise RuntimeError('Ambiguous confirmation slot; never replay: '+str(d))
        else:
            pending.append((cid, rep))

    def terminate(signum, frame):
        nonlocal reason
        reason = 'user_immediate_stop'
        c.STOP.write_text('user_immediate_stop\n')

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        while pending or active:
            if c.STOP.exists() and reason is None:
                reason = 'user_stop'
            for _, d, _ in active.values():
                error = permanent_errors(d)
                if error and reason != 'quota_exhausted':
                    reason = error
            if reason in PERMANENT | {'user_immediate_stop'}:
                terminating = terminating or time.monotonic()
                stop_groups(active, time.monotonic()-terminating, sent)
            while pending and len(active) < 4 and reason is None:
                cid, rep = pending.pop(0)
                d = CONF_LOGS/cid/f'run-{rep:02d}'
                d.mkdir(parents=True)
                cmd = confirmation_command(cid, rep)
                c.writej(d/'started.json', dict(time=c.now(), candidate=cid, replicate=rep,
                    phase='confirmation', command=cmd,
                    protocol_commit=c.readj(CONF/'registration.json')['protocol_commit']))
                console = (d/'console.log').open('ab')
                env = os.environ.copy()
                env['CAMPAIGN_TRANSPORT_ERRORS'] = str(d/'transport-errors.jsonl')
                env['CAMPAIGN_STARTUP_MARKER'] = str(CONF_LOGS/'first-actor-request.json')
                proc = subprocess.Popen(cmd, cwd=c.ROOT, stdout=console, stderr=subprocess.STDOUT,
                    env=env, start_new_session=True, pass_fds=(lock_fd,))
                c.writej(d/'process.json', dict(pid=proc.pid, pgid=proc.pid, started=c.now()))
                active[(cid, rep)] = (proc, d, console)
                c.event('confirmation_episode_started', candidate=cid, replicate=rep, pid=proc.pid)
            finished = []
            for (cid, rep), (proc, d, console) in active.items():
                rc = proc.poll()
                if rc is None:
                    continue
                console.close()
                r = measure(d, CONF/'candidates'/cid, rc)
                r.update(candidate=cid, replicate=rep, phase='confirmation', returncode=rc, finished=c.now())
                if reason and not r.get('valid'):
                    r['interrupted_reason'] = reason
                c.writej(d/'result.json', r)
                c.event('confirmation_episode_finished', candidate=cid, replicate=rep,
                    clean=r.get('clean_complete'), error=r.get('error_class'), result_path=str(d/'result.json'))
                if r.get('error_class') and reason != 'quota_exhausted':
                    reason = r['error_class']
                finished.append((cid, rep))
            for slot in finished:
                del active[slot]
            if finished:
                confirmation_report(plan)
                phase_publish(c.readj(STATE))
            if reason and not active:
                break
            if active:
                time.sleep(2)
    finally:
        # Unexpected measurement/IO failure must not leave actors consuming quota.
        if active:
            for proc, _, console in active.values():
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            for proc, _, console in active.values():
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                console.close()
    confirmation_report(plan)
    c.writej(CONF/'finished.json', dict(time=c.now(), stop_reason=reason, unscheduled=pending))


def worker(mode, lock_fd):
    c.LOCK_FD = lock_fd
    if mode == 'confirmation':
        confirmation_execute(lock_fd)
        return
    # Native tick runs in its own worker so the wall-clock controller can cancel
    # the entire native generation at the exploration deadline.
    def terminate(signum, frame):
        if c.NATIVE_CHILD and c.NATIVE_CHILD.poll() is None:
            os.killpg(c.NATIVE_CHILD.pid, signal.SIGTERM)
            try:
                c.NATIVE_CHILD.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(c.NATIVE_CHILD.pid, signal.SIGKILL)
                c.NATIVE_CHILD.wait()
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    state = c.readj(A/'research-state.json')
    proposals = c.native_tick(state)
    c.writej(A/'phase-tick-result.json', dict(proposals=proposals, state=state))


def escalate_exploration(batch_id, executor_pid, elapsed, sent):
    """Escalate cancellation even if legacy error handling changes its stop reason."""
    if elapsed < 30:
        return
    sig = signal.SIGKILL if elapsed >= 60 else signal.SIGTERM
    batch = next(b for b in c.readj(A/'research-state.json')['batches'] if b['id'] == batch_id)
    for cid, rep in batch['schedule']:
        directory = c.LOGS/cid/f'run-{rep:02d}'
        process = directory/'process.json'
        if not process.exists() or (directory/'result.json').exists():
            continue
        pid = c.readj(process)['pid']
        if (pid, sig) in sent:
            continue
        try:
            # PID reuse must never signal another workload. All three independent
            # identity checks are required before touching this actor group.
            argv = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
            stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
            if (str(A/'actor.py').encode() in argv and str(directory).encode() in argv
                    and int(stat[1]) == executor_pid and os.getpgid(pid) == pid):
                os.killpg(pid, sig)
                sent.add((pid, sig))
        except (FileNotFoundError, ProcessLookupError):
            continue


def run_child(cmd, lock_fd, request=None):
    global CHILD
    env = os.environ.copy()
    env['CAMPAIGN_LOCK_FD'] = str(lock_fd)
    CHILD = subprocess.Popen(cmd, cwd=c.ROOT, env=env, pass_fds=(lock_fd,))
    cutoff = False
    cutoff_started = None
    sent = set()
    try:
        while CHILD.poll() is None:
            if request and expired(request) and not cutoff:
                cutoff = True
                cutoff_started = time.monotonic()
                c.event('exploration_deadline_reached', deadline=request['exploration_deadline'], child_pid=CHILD.pid)
                CHILD.terminate()
            if cutoff and '--id' in cmd:
                escalate_exploration(cmd[cmd.index('--id')+1], CHILD.pid,
                                     time.monotonic()-cutoff_started, sent)
            time.sleep(1)
        return CHILD.returncode, cutoff
    finally:
        CHILD = None


def deadline_reconcile(state, batch, request=None):
    """Cancellation errors stay on disk but don't masquerade as quota exhaustion."""
    permanent = state.get('stop_reason') if state.get('stop_reason') in PERMANENT else None
    previous_failure = None
    for cid in batch['candidates']:
        for rep in (1, 2, 3):
            d = c.LOGS/cid/f'run-{rep:02d}'
            error = permanent_errors(d)
            if error and permanent != 'quota_exhausted':
                permanent = error
            result = d/'result.json'
            if request and result.exists():
                outcome = c.readj(result)
                if (outcome.get('error_class') and outcome.get('finished')
                        and timestamp(outcome['finished']) < timestamp(request['exploration_deadline'])):
                    previous_failure = outcome['error_class']
    if permanent:
        state['status'] = state['stop_reason'] = permanent
        return permanent
    if previous_failure:
        state['status'] = state['stop_reason'] = previous_failure
        return previous_failure
    batch['cutoff'] = 'exploration_deadline'
    state['status'] = 'exploration_complete'
    state['stop_reason'] = None
    c.event('exploration_cutoff_reconciled', batch=batch['id'],
            original_summary=batch.get('summary'), interpretation='Intentional cutoff; incomplete outcomes excluded from selection.')
    return None


def controller():
    request = c.readj(REQUEST)
    if STATE.exists():
        raise RuntimeError('Existing phased controller state requires explicit reconciliation, never duplicate launch')
    phase = dict(phase='handoff', started=c.now(), exploration_deadline=request['exploration_deadline'],
                 controller_pid=os.getpid(), stop_reason=None)
    phase_publish(phase)
    (A/'phased.pid').write_text(str(os.getpid())+'\n')

    def terminate(signum, frame):
        c.STOP.write_text('user_immediate_stop\n')
        if CHILD and CHILD.poll() is None:
            CHILD.terminate()
        phase['stop_requested'] = True

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    with (A/'supervisor.lock').open('a') as lock:
        sent = False
        # The old supervisor owns this lock until its active batch has drained and
        # final state has been committed. Never mutate its state while it runs.
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if phase.get('stop_requested'):
                    phase['phase'] = phase['stop_reason'] = 'user_stop'
                    phase_publish(phase)
                    return
                if expired(request) and not sent:
                    pid = request['old_supervisor_pid']
                    cmdline = Path(f'/proc/{pid}/cmdline')
                    if cmdline.exists() and b'autoresearch/campaign.py\x00supervise' in cmdline.read_bytes():
                        os.kill(pid, signal.SIGTERM)
                        sent = True
                    else:
                        raise RuntimeError('Cannot verify legacy supervisor identity at deadline')
                time.sleep(2)
        c.LOCK_FD = lock.fileno()
        state = c.readj(A/'research-state.json')
        try:
            if c.STOP.read_text().strip() != HANDOFF:
                raise RuntimeError('STOP changed during handoff; preserving stop request')
            if state['status'] != 'user_stop' and not sent:
                raise RuntimeError('Legacy runner did not stop normally for handoff: '+state['status'])
            if sent:
                if deadline_reconcile(state, state['batches'][-1], request):
                    raise RuntimeError('Permanent transport error during deadline handoff')
            c.STOP.unlink()
            state['status'] = 'running'
            state['stop_reason'] = None
            state['supervisor_pid'] = os.getpid()
            (A/'supervisor.pid').write_text(str(os.getpid())+'\n')
            state['phase_controller'] = str(STATE)
            c.writej(A/'research-state.json', state)
            c.event('phased_handoff_complete', controller_pid=os.getpid(), previous_pid=request['old_supervisor_pid'])
            phase['phase'] = 'exploration'
            phase_publish(phase)

            while not expired(request) and not c.STOP.exists():
                p = priority(request)
                fp = c.fingerprint((A/'original-task.txt').read_text().replace(c.OPENING, p['opening'], 1), None)
                assigned = any(v['fingerprint'] == fp for v in state['candidates'].values())
                if not assigned:
                    proposals = [p]
                else:
                    result_path = A/'phase-tick-result.json'
                    if result_path.exists():
                        result_path.unlink()
                    rc, cutoff = run_child([c.PY, str(Path(__file__)), 'tick'], lock.fileno(), request)
                    if cutoff:
                        break
                    if rc or not result_path.exists():
                        raise RuntimeError('Native tick worker failed; no replay')
                    result = c.readj(result_path)
                    state, proposals = result['state'], result['proposals']
                    if proposals is None:
                        break
                    if any(p['opening'] == request['excluded_opening'] for p in proposals):
                        raise RuntimeError('Director proposed the explicitly excluded opening')
                if expired(request) or c.STOP.exists():
                    break
                batch = c.freeze(state, proposals)
                if expired(request):
                    # Protocol exists, but no actor has started; preserve all three
                    # assigned slots as unrun rather than leaking beyond cutoff.
                    batch['status'] = 'stopped'
                    batch['cutoff'] = 'exploration_deadline_before_launch'
                    break
                batch['status'] = 'running'
                c.writej(A/'research-state.json', state)
                c.report(state)
                phase_publish(phase)
                rc, cutoff = run_child([c.PY, str(A/'campaign.py'), 'batch', '--id', batch['id']], lock.fileno(), request)
                if rc:
                    raise RuntimeError('Exploration executor failed; preserve partial slots, no replay')
                c.ingest(state, batch)
                if cutoff:
                    permanent = deadline_reconcile(state, batch, request)
                    if not permanent and c.STOP.exists() and c.STOP.read_text().strip() == '':
                        c.STOP.unlink()  # legacy executor's deliberate deadline marker
                    break
                if state.get('stop_reason'):
                    break
                phase_publish(phase)

            if state.get('stop_reason') or c.STOP.exists() or phase.get('stop_requested'):
                phase['phase'] = 'stopped'
                phase['stop_reason'] = state.get('stop_reason') or 'user_stop'
            else:
                state['status'] = 'exploration_complete'
                state['stop_reason'] = None
                c.writej(A/'research-state.json', state)
                c.report(state)
                c.commit('research(results): exploration closed at fixed five-hour cutoff', c.result_paths())
                plan = confirmation_freeze(state, request)
                phase['phase'] = 'confirmation'
                phase['selected_candidates'] = plan['candidates']
                phase['confirmation_started'] = c.now()
                confirmation_report(plan)
                phase_publish(phase)
                rc, _ = run_child([c.PY, str(Path(__file__)), 'confirmation'], lock.fileno())
                if rc:
                    raise RuntimeError('Confirmation executor failed; preserve slots, no replay')
                finished = c.readj(CONF/'finished.json')
                if finished['stop_reason'] is None:
                    assert not finished['unscheduled']
                    assert all((CONF_LOGS/cid/f'run-{rep:02d}'/'result.json').exists()
                               for cid, rep in plan['schedule']), 'Confirmation ended with missing assigned results'
                phase['stop_reason'] = finished['stop_reason']
                phase['phase'] = 'completed' if finished['stop_reason'] is None else 'stopped'
                state['status'] = 'completed' if phase['phase'] == 'completed' else finished['stop_reason']
                state['stop_reason'] = finished['stop_reason']
                c.writej(A/'research-state.json', state)
        except Exception as exc:
            phase['phase'] = 'blocked'
            phase['stop_reason'] = repr(exc)
            phase['traceback'] = traceback.format_exc()
            c.event('phased_controller_error', error=repr(exc), traceback=phase['traceback'])
        finally:
            phase['finished'] = c.now()
            phase_publish(phase)
            paths = [STATE, A/'research-state.json', A/'research-log.jsonl', A/'to_human']
            if CONF.exists():
                paths.append(CONF)
            c.commit('research(status): phased campaign '+phase['phase'], paths)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['supervise', 'tick', 'confirmation'])
    args = parser.parse_args()
    if args.mode == 'supervise':
        # Separate startup guard: the legacy lock remains occupied during handoff.
        with (A/'phased.lock').open('a') as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                controller()
            except Exception as exc:
                if STATE.exists():
                    phase = c.readj(STATE)
                    if phase.get('controller_pid') == os.getpid():
                        phase.update(phase='blocked', stop_reason=repr(exc), traceback=traceback.format_exc())
                        phase_publish(phase)
                raise
    else:
        worker(args.mode, int(os.environ['CAMPAIGN_LOCK_FD']))


if __name__ == '__main__':
    main()
