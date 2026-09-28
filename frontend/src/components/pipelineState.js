export const AGENT_STAGES = ['research', 'debate', 'backtest', 'risk']

export function deriveStageStates(stages, ctx) {
  const {
    audit,
    approval,
    riskFailed = false,
    riskHasWarnings = false,
    pipelineFailed = false,
  } = ctx
  const records = Array.isArray(audit) ? audit : []
  let failureSeen = false
  return stages.map((s) => {
    const rec = records.find((a) => a.agent_name === s.k) || null
    const done = !!rec

    if (pipelineFailed) {
      if (AGENT_STAGES.includes(s.k)) {
        if (done) {
          if (s.k === 'risk' && (riskFailed || riskHasWarnings)) {
            return { status: 'COMPLETED*', tone: 'amber', done: true, rec, warning: true }
          }
          return { status: 'COMPLETED', tone: 'green', done: true, rec }
        }
        if (!failureSeen) {
          failureSeen = true
          return { status: 'FAILED', tone: 'red', done: false, rec: null, failed: true }
        }
        return { status: 'BLOCKED', tone: 'muted', done: false, rec: null, blocked: true }
      }
      return { status: 'BLOCKED', tone: 'muted', done: false, rec: null, blocked: true }
    }

    if (s.k === 'human_approval') {
      if (approval === 'pending') return { status: 'AWAITING', tone: 'amber', done: true, rec, awaiting: true }
      if (approval === 'approved') {
        if (riskFailed || riskHasWarnings) return { status: 'APPROVED*', tone: 'amber', done: true, rec, warning: true }
        return { status: 'APPROVED', tone: 'green', done: true, rec }
      }
      if (approval === 'rejected') return { status: 'REJECTED', tone: 'red', done: true, rec }
      return { status: 'PENDING', tone: 'muted', done, rec }
    }
    if ((s.k === 'paper_execution' || s.k === 'review') && !done && approval !== 'approved') {
      return { status: approval === 'rejected' ? 'BLOCKED' : 'PENDING', tone: 'muted', done: false, rec: null }
    }
    if (!done) return { status: 'PENDING', tone: 'muted', done: false, rec: null }
    if (s.k === 'risk' && (riskFailed || riskHasWarnings)) {
      return { status: 'COMPLETED*', tone: 'amber', done: true, rec, warning: true }
    }
    return { status: 'COMPLETED', tone: 'green', done: true, rec }
  })
}
