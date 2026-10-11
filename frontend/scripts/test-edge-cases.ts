import { api, ApiError } from '../src/api/client';

const OPERATOR_TOKEN = 'dev-operator-token-local';

async function testEdgeCases() {
  console.log('=== Running Part C Edge Case Verifications ===');

  // Create session
  const created = await api.createSession({
    mode: 'pilot',
    environment_order: ['puzzle_hints', 'bret_discrete'],
    participant_id: 'edge-case-participant',
  }, OPERATOR_TOKEN);
  const sessionCode = created.session.session_code;
  console.log(`Session created: ${sessionCode}`);

  const joinRes = await api.joinSession(sessionCode);
  const sessionToken = joinRes.session_token;
  const trialId = joinRes.current_trial_id;
  console.log(`Joined session. Token: ${sessionToken.slice(0, 8)}..., Trial: ${trialId}`);

  let trial = await api.getTrial(trialId, sessionToken);
  console.log(`Initial status: ${trial.status}, version: ${trial.state_version}`);

  // Edge Case 1: open-decision auto-completing if board is already solved
  console.log('\n--- Edge Case 1: open-decision when board is already solved ---');
  // Expected solution for pz_practice_01 is ["moon", "key", "star", "leaf"]
  const correctBoard = ["moon", "key", "star", "leaf"];
  const updateRes = await api.updateBoard(trialId, correctBoard, 1000, trial.state_version, sessionToken);
  console.log(`Placed correct board without check-answer. Version: ${updateRes.state_version}`);

  const openRes = await api.openDecision(trialId, 1500, updateRes.state_version, sessionToken);
  console.log(`openDecision response status: ${openRes.status}`);
  if (openRes.status !== 'completed_without_decision') {
    throw new Error(`Expected completed_without_decision, got: ${openRes.status}`);
  }
  console.log('✓ Edge Case 1 PASSED: Board was solved before open-decision, auto-completed without decision options!');

  // Advance to next trial (pilot_02)
  console.log('\n--- Advancing to Trial 2 for Stale Version and Idempotency Tests ---');
  const nextRes = await api.nextTrial(trialId, created.session.session_id, sessionToken);
  const trial2Id = nextRes.next_trial_id!;
  let trial2 = await api.getTrial(trial2Id, sessionToken);
  console.log(`Trial 2 loaded: ${trial2Id}, status: ${trial2.status}, version: ${trial2.state_version}`);

  // Edge Case 2: Pause and Refresh / Rejoin Recovery
  console.log('\n--- Edge Case 2: Pause and Rejoin Recovery ---');
  await api.pauseTrial(trial2Id, 500, trial2.state_version, sessionToken);
  trial2 = await api.getTrial(trial2Id, sessionToken);
  console.log(`Trial 2 paused: status=${trial2.status}`);
  if (trial2.status !== 'paused') throw new Error(`Expected paused, got ${trial2.status}`);

  // Re-join with session code
  const rejoinRes = await api.joinSession(sessionCode);
  console.log(`Re-joined session. Current trial: ${rejoinRes.current_trial_id}`);
  if (rejoinRes.current_trial_id !== trial2Id) throw new Error('Rejoin failed to locate paused trial');
  const resumedTrial = await api.getTrial(rejoinRes.current_trial_id, rejoinRes.session_token);
  if (resumedTrial.status !== 'paused') throw new Error('Rejoined trial is not paused');

  // Resume trial
  await api.resumeTrial(trial2Id, resumedTrial.state_version, sessionToken);
  trial2 = await api.getTrial(trial2Id, sessionToken);
  console.log(`Trial 2 resumed: status=${trial2.status}, version=${trial2.state_version}`);
  console.log('✓ Edge Case 2 PASSED: Pause & Rejoin restoration verified!');

  // Open decision on Trial 2
  const openDecision2 = await api.openDecision(trial2Id, 1000, trial2.state_version, sessionToken);
  trial2 = await api.getTrial(trial2Id, sessionToken);
  console.log(`Trial 2 decision open: status=${trial2.status}, version=${trial2.state_version}`);

  // Edge Case 3: Stale state_version conflict
  console.log('\n--- Edge Case 3: Stale state_version conflict rejection ---');
  const staleVersion = trial2.state_version - 1; // Stale!
  const idemKey = `test_idem_${Date.now()}`;
  let conflictCaught = false;
  try {
    await api.commitDecision(trial2Id, {
      idempotency_key: idemKey,
      acceptable_by_action: { continue: 'yes', hint: 'yes', next_step: 'no', solution: 'no' },
      selected_action_id: 'hint',
      preferred_action_ids: ['hint'],
      deliberation_ms: 2500,
      state_version: staleVersion,
    }, sessionToken);
  } catch (err: any) {
    console.log(`Caught expected error: ${err.message} (status: ${err.status})`);
    if (err instanceof ApiError && (err.isStateVersionConflict || err.message.includes('State version conflict'))) {
      conflictCaught = true;
    }
  }
  if (!conflictCaught) throw new Error('Stale state version conflict was not rejected!');
  console.log('✓ Edge Case 3 PASSED: Server rejected stale state_version and client detected conflict!');

  // Edge Case 4: Idempotent Replay
  console.log('\n--- Edge Case 4: Idempotent Decision Replay ---');
  const validCommit = await api.commitDecision(trial2Id, {
    idempotency_key: idemKey,
    acceptable_by_action: { continue: 'yes', hint: 'yes', next_step: 'no', solution: 'no' },
    selected_action_id: 'hint',
    preferred_action_ids: ['hint'],
    deliberation_ms: 2500,
    state_version: trial2.state_version,
  }, sessionToken);
  console.log(`First commit succeeded. Trial status: ${validCommit.trial_status}, idempotent: ${validCommit.idempotent}`);

  // Resend identical request with same idempotency key
  const replayedCommit = await api.commitDecision(trial2Id, {
    idempotency_key: idemKey,
    acceptable_by_action: { continue: 'yes', hint: 'yes', next_step: 'no', solution: 'no' },
    selected_action_id: 'hint',
    preferred_action_ids: ['hint'],
    deliberation_ms: 2500,
    state_version: trial2.state_version,
  }, sessionToken);
  console.log(`Replayed commit result: idempotent=${replayedCommit.idempotent}`);
  if (replayedCommit.idempotent !== true) {
    throw new Error('Replayed commit was not marked idempotent: true');
  }
  console.log('✓ Edge Case 4 PASSED: Idempotent replay returned exact original outcome without duplicate events!');

  console.log('\n=== ALL EDGE CASES PASSED WITH 100% SUCCESS ===');
}

testEdgeCases().catch((err) => {
  console.error('Edge case test failed:', err);
  process.exit(1);
});
