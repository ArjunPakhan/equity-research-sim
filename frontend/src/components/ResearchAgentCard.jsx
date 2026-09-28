import { useState } from 'react'
import DataProvenance from './DataProvenance.jsx'

function val(v) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'number' && isNaN(v)) return 'UNAVAILABLE'
  return v
}
function row(label, value) {
  return (
    <div className="metric">
      <span>{label}</span>
      <span style={{ textAlign: 'right', maxWidth: '65%' }}>{val(value)}</span>
    </div>
  )
}

export default function ResearchAgentCard({ rec, bt }) {
  const [showRaw, setShowRaw] = useState(false)
  if (!rec) return null
  const o = rec.output_json || {}
  const warnings = Array.isArray(o.data_warnings) ? o.data_warnings : []
  const levels = Array.isArray(o.key_levels) ? o.key_levels : (o.key_levels !== undefined ? [o.key_levels] : [])
  const quality = o.data_quality && typeof o.data_quality === 'object' ? o.data_quality : null
  const timestamp = rec.timestamp || o.generated_at

  return (
    <div className="card" style={{ marginTop: 8 }}>
      <div className="card-h">RESEARCH AGENT</div>
      {row('STATUS', rec.human_approval_status === 'approved' ? 'COMPLETED (APPROVED)' : 'COMPLETED')}
      {row('TIMESTAMP', timestamp ? String(timestamp).slice(0, 19).replace('T', ' ') : null)}
      {row('TICKER', o.resolved_ticker || o.ticker)}
      {row('TREND', o.trend)}
      <DataProvenance rec={rec} bt={bt} />
      {row('KEY LEVELS', levels.length ? levels.join(', ') : (o.key_levels ?? null))}
      <div className="metric" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
        <span style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>DATA WARNINGS</span>
        {warnings.length ? warnings.map((w, i) => (
          <span key={i} className="mono" style={{ fontSize: 11, color: 'var(--amber)', paddingLeft: 4 }}>• {val(w)}</span>
        )) : <span className="mono" style={{ fontSize: 11 }}>{val(o.data_warnings)}</span>}
      </div>
      {quality ? (
        <div className="metric" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
          <span style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>DATA QUALITY</span>
          {Object.entries(quality).map(([k, v]) => (
            <span key={k} className="mono" style={{ fontSize: 11, paddingLeft: 4 }}>{k}: {val(typeof v === 'number' || typeof v === 'string' ? v : JSON.stringify(v))}</span>
          ))}
        </div>
      ) : (
        row('DATA QUALITY', o.data_quality ?? null)
      )}
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
