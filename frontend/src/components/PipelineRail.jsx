import { useEffect, useRef, useState } from 'react'
import ResearchAgentCard from './ResearchAgentCard.jsx'
import DebateAgentCard from './DebateAgentCard.jsx'
import BacktestAgentCard from './BacktestAgentCard.jsx'
import RiskAgentCard from './RiskAgentCard.jsx'

const DEFAULT_STAGES = [
  { k: 'research', label: 'Research' },
  { k: 'debate', label: 'Debate' },
  { k: 'backtest', label: 'Backtest' },
  { k: 'risk', label: 'Risk' },
  { k: 'human_approval', label: 'Human Approval' },
  { k: 'paper_execution', label: 'Paper Execution' },
  { k: 'review', label: 'Review' },
]

function getRec(audit, k) {
  return audit.find((a) => a.agent_name === k)
}

function getResearchOhlc(audit) {
  const rec = getRec(audit, 'research')
  const input = rec && rec.input_json
  const data = input && input.ohlc && input.ohlc.data
  return Array.isArray(data) ? data : null
}

function compactSummary(rec) {
  if (!rec || !rec.output_json) return null
  const o = rec.output_json
  // Risk: surface warnings/checks
  if (rec.agent_name === 'risk') {
    const parts = []
    if (typeof o.checks_passed === 'boolean') parts.push(`checks ${o.checks_passed ? 'PASSED' : 'FAILED'}`)
    if (typeof o.position_size === 'number') parts.push(`size ${o.position_size}%`)
    if (o.sebi_aligned_controls) parts.push(`${o.sebi_aligned_controls.length} controls`)
    if (o.risk_warnings) parts.push(`${o.risk_warnings.length} warnings`)
    return parts.join(' · ')
  }
  if (rec.agent_name === 'backtest') {
    const parts = []
    if (o.trade_count !== undefined) parts.push(`${o.trade_count} trades`)
    if (o.total_return_pct !== undefined && o.total_return_pct !== null) parts.push(`${Number(o.total_return_pct).toFixed(2)}%`)
    if (o.win_rate !== undefined && o.win_rate !== null) parts.push(`win ${(o.win_rate*100).toFixed(1)}%`)
    if (o.max_drawdown !== undefined && o.max_drawdown !== null) parts.push(`dd ${Number(o.max_drawdown).toFixed(2)}%`)
    return parts.join(' · ') || null
  }
  if (rec.agent_name === 'research' && o.trend) return `trend: ${o.trend}`
  if (rec.agent_name === 'debate' && o.biases_flagged) return `${o.biases_flagged.length} biases flagged`
  if (rec.agent_name === 'paper_execution' && o.execution_status) return `${o.execution_status} · ${o.execution_type || ''}`
  if (rec.agent_name === 'review' && o.summary) return String(o.summary).slice(0,120)
  return null
}

export default function PipelineRail({ audit, approval, stages = DEFAULT_STAGES }) {
  const [selected, setSelected] = useState(null)
  const [showRaw, setShowRaw] = useState(false)
  const [flash, setFlash] = useState({})
  const prevSigRef = useRef(null)
  const flashTimerRef = useRef(null)

  const riskRec = getRec(audit, 'risk')
  const riskFailed = riskRec && riskRec.output_json && riskRec.output_json.checks_passed === false
  const riskHasWarnings = riskRec && riskRec.output_json && Array.isArray(riskRec.output_json.risk_warnings) && riskRec.output_json.risk_warnings.length > 0

  function stageState(s) {
    const rec = getRec(audit, s.k)
    const done = !!rec
    if (s.k === 'human_approval') {
      if (approval === 'pending') return { status: 'AWAITING', tone: 'amber', done: true, rec, awaiting: true }
      if (approval === 'approved') {
        // warning if risk failed but approved
        if (riskFailed || riskHasWarnings) return { status: 'APPROVED*', tone: 'amber', done: true, rec, warning: true }
        return { status: 'APPROVED', tone: 'green', done: true, rec }
      }
      if (approval === 'rejected') return { status: 'REJECTED', tone: 'red', done: true, rec }
      return { status: 'PENDING', tone: 'muted', done, rec }
    }
    // Paper execution / review must not read as active before human authorization
    if ((s.k === 'paper_execution' || s.k === 'review') && !done && approval !== 'approved') {
      return { status: approval === 'rejected' ? 'BLOCKED' : 'PENDING', tone: 'muted', done: false, rec: null }
    }
    if (!done) return { status: 'PENDING', tone: 'muted', done: false, rec: null }
    // warning for risk
    if (s.k === 'risk' && (riskFailed || riskHasWarnings)) return { status: 'COMPLETED*', tone: 'amber', done: true, rec, warning: true }
    return { status: 'COMPLETED', tone: 'green', done: true, rec }
  }

  // One-shot completion / approval flashes — only when a stage signature actually changes after first observation
  useEffect(() => {
    const sigs = {}
    const newly = []
    for (const s of stages) {
      const st = stageState(s)
      const sig = `${st.status}|${st.tone}|${st.done ? 1 : 0}|${st.warning ? 1 : 0}`
      sigs[s.k] = sig
      const prev = prevSigRef.current
      if (prev && prev[s.k] !== undefined && prev[s.k] !== sig && st.done) {
        newly.push(s.k)
      }
    }
    prevSigRef.current = sigs
    if (newly.length === 0) return
    setFlash((f) => {
      const next = { ...f }
      for (const k of newly) next[k] = (next[k] || 0) + 1
      return next
    })
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current)
    flashTimerRef.current = setTimeout(() => setFlash({}), 280)
  }, [audit, approval, stages])

  useEffect(() => () => {
    if (flashTimerRef.current) clearTimeout(flashTimerRef.current)
  }, [])

  const researchOhlc = getResearchOhlc(audit)
  const selectedRec = selected ? getRec(audit, selected) : null
  const approvalGateOpen = approval === 'approved'

  return (
    <div className="card">
      <div className="card-h">PIPELINE — EXECUTION FLOW</div>

      <style>{`
        .pr-rail{ display:flex; align-items:stretch; gap:0; overflow-x:auto; padding:8px 2px 10px; scrollbar-width:thin;}
        .pr-node-wrap{ display:flex; align-items:center; flex:1; min-width:0; }
        .pr-node{ flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; padding:10px 6px; border:1px solid var(--border); background:var(--card); cursor:pointer; min-height:78px; justify-content:center; position:relative; transition:border-color 180ms cubic-bezier(0.23,1,0.32,1), background-color 180ms cubic-bezier(0.23,1,0.32,1), opacity 180ms ease-out, transform 180ms cubic-bezier(0.23,1,0.32,1); font-family:var(--mono); text-align:center; }
        .pr-node:disabled{ cursor:default; opacity:0.45; }
        .pr-node:focus-visible{ outline:1px solid var(--amber); outline-offset:2px; }
        .pr-node.green{ border-color:var(--green); background:rgba(0,200,83,0.08); }
        .pr-node.amber{ border-color:var(--amber); background:var(--amber-glow); }
        .pr-node.red{ border-color:var(--red); background:rgba(255,61,0,0.08); }
        .pr-node.muted{ border-color:var(--border); opacity:0.6; }
        .pr-node.warning{ box-shadow:0 0 0 1px var(--amber) inset; }
        .pr-node.awaiting{ box-shadow:0 0 0 1px var(--amber) inset; }
        .pr-node.selected{ box-shadow:0 0 0 1px var(--amber) inset; }
        .pr-node.pr-anim{ animation:pr-complete-in 200ms cubic-bezier(0.23,1,0.32,1) 1; }
        .pr-dot{ width:10px; height:10px; border-radius:50%; flex-shrink:0; transition:background-color 180ms ease-out, box-shadow 180ms ease-out, transform 180ms cubic-bezier(0.23,1,0.32,1); }
        .pr-dot.green{ background:var(--green); box-shadow:0 0 6px rgba(0,200,83,0.5);}
        .pr-dot.amber{ background:var(--amber); box-shadow:0 0 6px rgba(255,176,0,0.5);}
        .pr-dot.red{ background:var(--red); box-shadow:0 0 6px rgba(255,61,0,0.5);}
        .pr-dot.muted{ background:#333; box-shadow:none; }
        .pr-dot.pr-anim{ animation:pr-dot-settle 220ms cubic-bezier(0.23,1,0.32,1) 1; }
        .pr-label{ font-size:10px; letter-spacing:0.06em; font-weight:600; line-height:1.2; }
        .pr-status{ font-size:9px; letter-spacing:0.06em; transition:color 180ms ease-out, opacity 180ms ease-out; }
        .pr-status.green{ color:var(--green); }
        .pr-status.amber{ color:var(--amber); }
        .pr-status.red{ color:var(--red); }
        .pr-status.muted{ color:var(--muted); }
        .pr-connector{ width:18px; height:2px; flex-shrink:0; margin:0 1px; align-self:center; position:relative; overflow:hidden; transition:background-color 180ms ease-out; }
        .pr-connector.green{ background:var(--green); }
        .pr-connector.amber{ background:var(--amber); }
        .pr-connector.red{ background:var(--red); }
        .pr-connector.muted{ background:var(--border); }
        .pr-connector.pr-flow::after{ content:''; position:absolute; inset:0; background:rgba(232,232,216,0.45); transform:translateX(-110%); animation:pr-connector-sweep 200ms cubic-bezier(0.23,1,0.32,1) 1 forwards; }
        .pr-detail{ margin-top:10px; border:1px solid var(--border); background:#0d120d; padding:10px; }
        .pr-detail-h{ font-family:var(--mono); font-size:10px; letter-spacing:0.08em; color:var(--amber); margin-bottom:6px; display:flex; justify-content:space-between; }
        .pr-raw-toggle{ font-family:var(--mono); font-size:10px; letter-spacing:0.06em; color:var(--amber); background:transparent; border:1px solid var(--border); padding:4px 8px; cursor:pointer; margin-top:8px; transition:border-color 150ms ease-out, background-color 150ms ease-out, color 150ms ease-out, transform 120ms cubic-bezier(0.23,1,0.32,1); }
        .pr-raw-toggle:hover{ border-color:var(--amber); }
        .pr-raw-toggle:active{ transform:scale(0.97); }
        .pr-raw-toggle:focus-visible{ outline:1px solid var(--amber); outline-offset:1px; }
        @keyframes pr-complete-in{
          0%{ transform:scale(0.97); opacity:0.75; }
          100%{ transform:scale(1); opacity:1; }
        }
        @keyframes pr-dot-settle{
          0%{ transform:scale(0.85); }
          100%{ transform:scale(1); }
        }
        @keyframes pr-connector-sweep{
          0%{ transform:translateX(-110%); opacity:0.5; }
          100%{ transform:translateX(110%); opacity:0; }
        }
        @media (prefers-reduced-motion: reduce){
          .pr-node, .pr-dot, .pr-status, .pr-connector, .pr-raw-toggle{ transition:none !important; animation:none !important; }
          .pr-node.pr-anim, .pr-dot.pr-anim, .pr-connector.pr-flow::after{ animation:none !important; transform:none !important; opacity:1 !important; }
          .pr-connector.pr-flow::after{ display:none; }
        }
        @media(max-width:900px){ .pr-rail{ flex-direction:column; } .pr-node-wrap{ flex-direction:column; } .pr-connector{ width:2px; height:14px; margin:1px 0; } .pr-connector.pr-flow::after{ transform:translateY(-110%); animation-name:pr-connector-sweep-y; } }
        @keyframes pr-connector-sweep-y{
          0%{ transform:translateY(-110%); opacity:0.5; }
          100%{ transform:translateY(110%); opacity:0; }
        }
      `}</style>

      <div className="pr-rail" role="list">
        {stages.map((s, i) => {
          const st = stageState(s)
          const isSelected = selected === s.k
          const canClick = !!st.rec
          const toneClass = st.tone
          const connectorTone = st.done ? (st.tone === 'red' ? 'red' : st.tone === 'amber' ? 'amber' : 'green') : 'muted'
          const nodeFlash = flash[s.k] != null
          const connectorFlash = nodeFlash && i < stages.length - 1
          const gated = (s.k === 'paper_execution' || s.k === 'review') && !approvalGateOpen && !st.done
          return (
            <div key={s.k} className="pr-node-wrap" role="listitem">
              <button
                type="button"
                className={`pr-node ${toneClass} ${st.warning ? 'warning' : ''} ${st.awaiting ? 'awaiting' : ''} ${isSelected ? 'selected' : ''} ${nodeFlash ? 'pr-anim' : ''} ${gated ? 'gated' : ''}`}
                onClick={() => canClick && (setSelected(isSelected ? null : s.k), setShowRaw(false))}
                disabled={!canClick}
                aria-pressed={isSelected}
                title={canClick ? `View ${s.label}` : `${s.label} pending`}
                style={isSelected ? { borderColor: 'var(--amber)' } : undefined}
              >
                <span className={`pr-dot ${st.tone} ${nodeFlash ? 'pr-anim' : ''}`} aria-hidden />
                <span className="pr-label">{s.label}</span>
                <span className={`pr-status ${st.tone}`} key={`${st.status}-${st.tone}`}>{st.warning ? '⚠ ' : ''}{st.status}</span>
                {s.k === 'risk' && (riskFailed || riskHasWarnings) && st.done && (
                  <span className="mono" style={{ fontSize: 9, color: 'var(--amber)' }}>{riskFailed ? 'CHECKS FAILED' : `${riskRec.output_json.risk_warnings.length} warnings`}</span>
                )}
                {s.k === 'human_approval' && st.warning && (
                  <span className="mono" style={{ fontSize: 9, color: 'var(--amber)' }}>RISK WARNING</span>
                )}
                {gated && (
                  <span className="mono" style={{ fontSize: 9, color: 'var(--muted)' }}>GATED</span>
                )}
              </button>
              {i < stages.length - 1 && (
                <div className={`pr-connector ${connectorTone} ${connectorFlash ? 'pr-flow' : ''}`} aria-hidden />
              )}
            </div>
          )
        })}
      </div>

      {selectedRec && selected === 'research' && <ResearchAgentCard rec={selectedRec} bt={getRec(audit, 'backtest')} />}
      {selectedRec && selected === 'debate' && <DebateAgentCard rec={selectedRec} />}
      {selectedRec && selected === 'backtest' && <BacktestAgentCard rec={selectedRec} ohlc={researchOhlc} />}
      {selectedRec && selected === 'risk' && <RiskAgentCard rec={selectedRec} />}
      {selectedRec && !['research', 'debate', 'backtest', 'risk'].includes(selected) && (
        <div className="pr-detail">
          <div className="pr-detail-h">
            <span>{selectedRec.agent_name.toUpperCase()} — {selectedRec.timestamp?.slice(0, 19).replace('T', ' ')}</span>
            <span style={{ color: selectedRec.human_approval_status === 'approved' ? 'var(--green)' : selectedRec.human_approval_status === 'rejected' ? 'var(--red)' : 'var(--amber)' }}>
              {selectedRec.human_approval_status || 'n/a'}
            </span>
          </div>
          {compactSummary(selectedRec) && (
            <div className="mono" style={{ fontSize: 11, color: 'var(--text)', marginBottom: 6 }}>{compactSummary(selectedRec)}</div>
          )}
          {selectedRec.agent_name === 'human_approval' && (riskFailed || riskHasWarnings) && (
            <div className="mono" style={{ fontSize: 10, color: 'var(--amber)', border: '1px solid #402a00', background: '#1a1200', padding: 6, marginTop: 6 }}>
              ⚠ Approved despite risk checks failed/warnings — see Risk details
            </div>
          )}
          <button type="button" className="pr-raw-toggle" onClick={() => setShowRaw(!showRaw)} aria-expanded={showRaw}>
            {showRaw ? 'HIDE RAW JSON' : 'VIEW RAW JSON'}
          </button>
          {showRaw && (
            <div className="json" style={{ marginTop: 8, maxHeight: 260 }}>
              {JSON.stringify({ input: selectedRec.input_json, output: selectedRec.output_json, approval: selectedRec.human_approval_status, approved_by: selectedRec.approved_by }, null, 2)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
