import { useState } from 'react'

function val(v) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'number' && isNaN(v)) return 'UNAVAILABLE'
  return v
}

export default function DebateAgentCard({ rec }) {
  const [showRaw, setShowRaw] = useState(false)
  if (!rec) return null
  const o = rec.output_json || {}
  const biases = Array.isArray(o.biases_flagged) ? o.biases_flagged : []
  const timestamp = rec.timestamp || o.generated_at
  const llmMode = o.llm_mode === 'real' || o.llm_mode === 'mock' ? o.llm_mode : null
  const llmModel = llmMode === 'mock'
    ? '—'
    : (llmMode === 'real' && typeof o.model === 'string' && o.model ? o.model : null)

  return (
    <div className="card" style={{ marginTop: 8 }}>
      <div className="card-h">DEBATE AGENT</div>
      <div className="metric">
        <span>STATUS</span>
        <span>{rec.human_approval_status === 'approved' ? 'COMPLETED (APPROVED)' : 'COMPLETED'}</span>
      </div>
      <div className="metric">
        <span>TIMESTAMP</span>
        <span>{timestamp ? String(timestamp).slice(0, 19).replace('T', ' ') : 'UNAVAILABLE'}</span>
      </div>
      <div className="metric">
        <span>LLM MODE</span>
        <span style={{ color: llmMode === 'real' ? 'var(--green)' : llmMode === 'mock' ? 'var(--amber)' : undefined }}>
          {llmMode ? llmMode.toUpperCase() : 'UNAVAILABLE'}
        </span>
      </div>
      <div className="metric">
        <span>LLM MODEL</span>
        <span style={{ textAlign: 'right', maxWidth: '65%' }}>{val(llmModel)}</span>
      </div>

      <div style={{ marginTop: 8, border: '1px solid var(--green)', padding: 8, background: 'rgba(0,200,83,0.05)' }}>
        <div className="mono" style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--green)', marginBottom: 4 }}>▲ BULL CASE</div>
        <div className="mono" style={{ fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text)' }}>
          {typeof o.bull_case === 'string' && o.bull_case ? o.bull_case : 'UNAVAILABLE'}
        </div>
      </div>

      <div style={{ marginTop: 8, border: '1px solid var(--red)', padding: 8, background: 'rgba(255,61,0,0.05)' }}>
        <div className="mono" style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--red)', marginBottom: 4 }}>▼ BEAR CASE</div>
        <div className="mono" style={{ fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text)' }}>
          {typeof o.bear_case === 'string' && o.bear_case ? o.bear_case : 'UNAVAILABLE'}
        </div>
      </div>

      <div style={{ marginTop: 8 }}>
        <div className="mono" style={{ fontSize: 10, letterSpacing: '0.1em', color: 'var(--amber)', marginBottom: 4 }}>BIAS DETECTION</div>
        {biases.length ? biases.map((b, i) => (
          <div key={i} className="mono" style={{ fontSize: 11, padding: '3px 0', borderBottom: '1px solid var(--border)' }}>• {typeof b === 'string' ? b : val(JSON.stringify(b))}</div>
        )) : <div className="mono" style={{ fontSize: 11 }}>{val(o.biases_flagged)}</div>}
      </div>

      <div className="metric" style={{ marginTop: 8 }}>
        <span>FAILURE CONDITIONS</span>
        <span style={{ textAlign: 'right', maxWidth: '65%' }}>{val(typeof o.failure_conditions === 'object' ? JSON.stringify(o.failure_conditions) : o.failure_conditions)}</span>
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
