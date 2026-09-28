import { useState } from 'react'

function val(v) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'number' && isNaN(v)) return 'UNAVAILABLE'
  if (typeof v === 'string' && v.includes('UNAVAILABLE')) return 'UNAVAILABLE'
  return v
}
function fmt(v, d = 2) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'string' && v.includes('UNAVAILABLE')) return 'UNAVAILABLE'
  if (typeof v === 'number') return v.toFixed(d)
  return String(v)
}
function row(label, value, color) {
  return (
    <div className="metric">
      <span>{label}</span>
      <span style={{ textAlign: 'right', maxWidth: '65%', color }}>{value}</span>
    </div>
  )
}

export default function RiskAgentCard({ rec }) {
  const [showRaw, setShowRaw] = useState(false)
  if (!rec) return null
  const o = rec.output_json || {}
  const warnings = Array.isArray(o.risk_warnings) ? o.risk_warnings : []
  const controls = Array.isArray(o.sebi_aligned_controls) ? o.sebi_aligned_controls : []
  const checks = typeof o.checks_passed === 'boolean' ? o.checks_passed : null
  const checkState = checks === false ? 'FAILED' : checks === true ? 'PASSED' : 'UNAVAILABLE'
  const checkColor = checks === false ? 'var(--red)' : checks === true ? 'var(--green)' : 'var(--muted)'
  const hasWarning = checks === true && warnings.length > 0

  return (
    <div className="card" style={{ marginTop: 8 }}>
      <div className="card-h">RISK AGENT</div>
      <div className="mono" style={{ fontSize: 10, letterSpacing: '0.06em', color: 'var(--amber)', border: '1px solid #402a00', background: '#1a1200', padding: '5px 7px', marginBottom: 8 }}>
        SIMULATION CONTROL — Not SEBI compliant — Educational only
      </div>

      {checks === false && (
        <div className="mono" style={{ fontSize: 11, border: '1px solid var(--red)', background: 'rgba(255,61,0,0.1)', color: 'var(--red)', padding: '7px 8px', marginBottom: 8, letterSpacing: '0.06em', fontWeight: 600 }}>
          ⚠ RISK CHECKS FAILED
        </div>
      )}
      {hasWarning && (
        <div className="mono" style={{ fontSize: 11, border: '1px solid var(--amber)', background: 'var(--amber-glow)', color: 'var(--amber)', padding: '7px 8px', marginBottom: 8, letterSpacing: '0.06em' }}>
          ⚠ WARNING — CHECKS PASSED WITH WARNINGS
        </div>
      )}

      {row('CHECKS PASSED', checkState, checkColor)}
      {row('TIMESTAMP', rec.timestamp ? String(rec.timestamp).slice(0, 19).replace('T', ' ') : null)}
      {row('POSITION SIZE', typeof o.position_size === 'number' ? `${fmt(o.position_size)}%` : val(o.position_size))}
      {row('STOP LOSS', typeof o.stop_loss === 'number' ? fmt(o.stop_loss) : val(o.stop_loss))}
      {row('EXPOSURE LIMIT', typeof o.exposure_limit === 'number' ? `${fmt(o.exposure_limit)}%` : val(o.exposure_limit))}
      {row('DAILY LOSS LIMIT', typeof o.daily_loss_limit === 'number' ? `${fmt(o.daily_loss_limit)}%` : val(o.daily_loss_limit))}

      <div className="metric" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>RISK WARNINGS</span>
        {warnings.length ? warnings.map((w, i) => (
          <span key={i} className="mono" style={{ fontSize: 11, color: 'var(--amber)', paddingLeft: 4 }}>• {val(w)}</span>
        )) : <span className="mono" style={{ fontSize: 11 }}>{val(o.risk_warnings)}</span>}
      </div>

      <div className="metric" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>CONTROLS (SEBI-INFORMED)</span>
        {controls.length ? controls.map((c, i) => (
          <span key={i} className="mono" style={{ fontSize: 11, paddingLeft: 4 }}>• {val(c)}</span>
        )) : <span className="mono" style={{ fontSize: 11 }}>{val(o.sebi_aligned_controls)}</span>}
      </div>

      <div className="metric" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>SIMULATION DISCLAIMER</span>
        <span className="mono" style={{ fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {val(o.simulation_disclaimer)}
        </span>
      </div>

      <button type="button" className="btn" style={{ marginTop: 8 }} onClick={() => setShowRaw(!showRaw)} aria-expanded={showRaw}>
        {showRaw ? 'HIDE RAW JSON' : 'VIEW RAW JSON'}
      </button>
      {showRaw && (
        <div className="json" style={{ marginTop: 8, maxHeight: 260 }}>
          {JSON.stringify({ input: rec.input_json, output: rec.output_json, approval: rec.human_approval_status, approved_by: rec.approved_by }, null, 2)}
        </div>
      )}
    </div>
  )
}
