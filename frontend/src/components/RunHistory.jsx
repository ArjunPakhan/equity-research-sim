function fmt(v, d = 2) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'string' && v.includes('UNAVAILABLE')) return 'UNAVAILABLE'
  if (typeof v === 'number') return v.toFixed(d)
  return String(v)
}

export default function RunHistory({ runs, selected, onSelect }) {
  return (
    <div className="card">
      <div className="card-h">RUN HISTORY — {runs.length}</div>
      {runs.length === 0 && <div className="dim mono" style={{ fontSize: 11 }}>No runs — create one</div>}
      {runs.map((r) => (
        <div
          key={r.run_id}
          className={`run-item ${selected === r.run_id ? 'active' : ''}`}
          onClick={() => onSelect(r.run_id)}
        >
          <div className="mono" style={{ fontSize: 11, fontWeight: 600 }}>
            {r.ticker} <span className="dim" style={{ fontSize: 10 }}>{r.run_id.slice(0, 8)}</span>
          </div>
          <div className="mono dim" style={{ fontSize: 10 }}>
            {r.created_at?.slice(0, 16).replace('T', ' ')} —{' '}
            <span style={r.pipeline_status === 'failed' ? { color: 'var(--red)' } : undefined}>{r.pipeline_status}</span>
          </div>
          <div style={{ marginTop: 4, display: 'flex', gap: 4 }}>
            <span
              className={`badge-status ${r.approval_status === 'approved' ? 'ok' : r.approval_status === 'rejected' ? 'bad' : 'warn'}`}
            >
              {r.approval_status}
            </span>
            {r.total_return_pct !== null && (
              <span className="mono dim" style={{ fontSize: 10 }}>
                {fmt(r.total_return_pct)}% · {r.trade_count} tr
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
