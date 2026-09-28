import { test } from 'node:test'
import assert from 'node:assert/strict'
import { deriveStageStates, AGENT_STAGES } from './pipelineState.js'

const STAGES = [
  { k: 'research', label: 'Research' },
  { k: 'debate', label: 'Debate' },
  { k: 'backtest', label: 'Backtest' },
  { k: 'risk', label: 'Risk' },
  { k: 'human_approval', label: 'Human Approval' },
  { k: 'paper_execution', label: 'Paper Execution' },
  { k: 'review', label: 'Review' },
]

const rec = (k) => ({ agent_name: k, output_json: {} })
const allAgents = [rec('research'), rec('debate'), rec('backtest'), rec('risk')]

test('healthy run awaiting approval: behavior unchanged', () => {
  const states = deriveStageStates(STAGES, {
    audit: [...allAgents, rec('human_approval')],
    approval: 'pending',
    pipelineFailed: false,
  })
  assert.deepEqual(states.map((s) => s.status), [
    'COMPLETED', 'COMPLETED', 'COMPLETED', 'COMPLETED', 'AWAITING', 'PENDING', 'PENDING',
  ])
})

test('failed at debate: research COMPLETED, debate FAILED, downstream + human BLOCKED', () => {
  const states = deriveStageStates(STAGES, {
    audit: [rec('research')],
    approval: 'n/a',
    pipelineFailed: true,
  })
  assert.deepEqual(states.map((s) => s.status), [
    'COMPLETED', 'FAILED', 'BLOCKED', 'BLOCKED', 'BLOCKED', 'BLOCKED', 'BLOCKED',
  ])
  assert.equal(states[1].tone, 'red')
  assert.equal(states[1].done, false)
  assert.equal(states[1].rec, null)
  assert.equal(states[4].tone, 'muted')
  assert.equal(states[4].done, false)
})

test('failed before research: research FAILED, everything else BLOCKED', () => {
  const states = deriveStageStates(STAGES, { audit: [], approval: 'n/a', pipelineFailed: true })
  assert.deepEqual(states.map((s) => s.status), [
    'FAILED', 'BLOCKED', 'BLOCKED', 'BLOCKED', 'BLOCKED', 'BLOCKED', 'BLOCKED',
  ])
  assert.equal(states[0].tone, 'red')
})

test('failed at backtest: research+debate COMPLETED, backtest FAILED, risk + human BLOCKED', () => {
  const states = deriveStageStates(STAGES, {
    audit: [rec('research'), rec('debate')],
    approval: 'n/a',
    pipelineFailed: true,
  })
  assert.deepEqual(states.map((s) => s.status), [
    'COMPLETED', 'COMPLETED', 'FAILED', 'BLOCKED', 'BLOCKED', 'BLOCKED', 'BLOCKED',
  ])
})

test('failed after all agents: agents COMPLETED, human BLOCKED (never AWAITING)', () => {
  const states = deriveStageStates(STAGES, {
    audit: [...allAgents, rec('human_approval')],
    approval: 'pending',
    pipelineFailed: true,
  })
  assert.deepEqual(states.map((s) => s.status), [
    'COMPLETED', 'COMPLETED', 'COMPLETED', 'COMPLETED', 'BLOCKED', 'BLOCKED', 'BLOCKED',
  ])
  assert.notEqual(states[4].status, 'AWAITING')
})

test('failed run with zero audit records: no stage reads as healthy', () => {
  const states = deriveStageStates(STAGES, { audit: [], approval: 'n/a', pipelineFailed: true })
  for (const s of states) {
    assert.notEqual(s.status, 'AWAITING')
    assert.notEqual(s.status, 'APPROVED')
    assert.notEqual(s.status, 'PENDING')
  }
})

test('failed + risk completed: risk shows COMPLETED warning variant', () => {
  const states = deriveStageStates(STAGES, {
    audit: allAgents,
    approval: 'n/a',
    riskHasWarnings: true,
    pipelineFailed: true,
  })
  assert.equal(states[3].status, 'COMPLETED*')
  assert.equal(states[3].tone, 'amber')
  assert.equal(states[3].warning, true)
})

test('healthy rejected approval: REJECTED human, BLOCKED paper execution', () => {
  const states = deriveStageStates(STAGES, {
    audit: [...allAgents, rec('human_approval')],
    approval: 'rejected',
    pipelineFailed: false,
  })
  assert.equal(states[4].status, 'REJECTED')
  assert.equal(states[5].status, 'BLOCKED')
  assert.equal(states[5].tone, 'muted')
})

test('healthy approved run: APPROVED human, paper+review pending', () => {
  const states = deriveStageStates(STAGES, {
    audit: [...allAgents, rec('human_approval')],
    approval: 'approved',
    pipelineFailed: false,
  })
  assert.equal(states[4].status, 'APPROVED')
  assert.equal(states[5].status, 'PENDING')
  assert.equal(states[6].status, 'PENDING')
})

test('AGENT_STAGES order matches rail stage order', () => {
  assert.deepEqual(AGENT_STAGES, ['research', 'debate', 'backtest', 'risk'])
})
