import { useMemo, useRef, useState } from 'react'

const VB_W = 640
const VB_H = 200
const PAD = { t: 16, r: 14, b: 28, l: 56 }

function finiteSeries(series) {
  if (!Array.isArray(series) || series.length === 0) return null
  const pts = []
  for (let i = 0; i < series.length; i++) {
    const v = series[i]
    if (typeof v === 'number' && Number.isFinite(v)) pts.push({ i, v })
  }
  return pts.length >= 1 ? pts : null
}

function fmtEq(v) {
  return `₹${v.toFixed(2)}`
}

function fmtBarDate(dates, i) {
  if (Array.isArray(dates) && dates[i] != null && dates[i] !== '') return String(dates[i])
  return null
}

export default function EquityCurveChart({ equityCurve, barDates }) {
  const svgRef = useRef(null)
  const [hover, setHover] = useState(null)

  const pts = useMemo(() => finiteSeries(equityCurve), [equityCurve])

  if (!pts) {
    return (
      <div className="card" style={{ marginTop: 8, padding: '10px 12px' }} role="img" aria-label="Equity curve data unavailable">
        <div className="card-h" style={{ marginBottom: 6 }}>EQUITY CURVE</div>
        <div className="mono" style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.08em' }}>DATA UNAVAILABLE</div>
      </div>
    )
  }

  const n = pts.length
  const rawMin = Math.min(...pts.map((p) => p.v))
  const rawMax = Math.max(...pts.map((p) => p.v))
  const span = rawMax - rawMin || 1
  const yMin = rawMin - span * 0.06
  const yMax = rawMax + span * 0.06
  const plotW = VB_W - PAD.l - PAD.r
  const plotH = VB_H - PAD.t - PAD.b

  const xOf = (idx) => PAD.l + (n === 1 ? plotW / 2 : (idx / (n - 1)) * plotW)
  const yOf = (v) => PAD.t + (1 - (v - yMin) / (yMax - yMin)) * plotH

  const path = pts.map((p, k) => `${k === 0 ? 'M' : 'L'}${xOf(k).toFixed(2)},${yOf(p.v).toFixed(2)}`).join(' ')
  const first = pts[0]
  const last = pts[n - 1]
  const gridY = [0, 0.25, 0.5, 0.75, 1].map((t) => ({
    y: PAD.t + t * plotH,
    label: (yMax - t * (yMax - yMin)).toFixed(0),
  }))

  const onMove = (e) => {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * VB_W
    const t = Math.min(1, Math.max(0, (x - PAD.l) / plotW))
    const k = Math.round(t * (n - 1))
    const p = pts[k]
    if (!p) return setHover(null)
    setHover({
      k,
      px: xOf(k),
      py: yOf(p.v),
      i: p.i,
      v: p.v,
      date: fmtBarDate(barDates, p.i),
    })
  }

  const tipLeft = hover ? Math.min(Math.max((hover.px / VB_W) * 100, 8), 72) : 0

  return (
    <div className="card" style={{ marginTop: 8, padding: '10px 12px', position: 'relative' }}>
      <div className="card-h" style={{ marginBottom: 6 }}>EQUITY CURVE</div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        width="100%"
        height="auto"
        style={{ display: 'block', maxHeight: 220, overflow: 'visible' }}
        role="img"
        aria-label={`Equity curve, ${n} bars, from ${fmtEq(first.v)} to ${fmtEq(last.v)}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {gridY.map((g) => (
          <g key={g.y}>
            <line x1={PAD.l} x2={VB_W - PAD.r} y1={g.y} y2={g.y} stroke="#2a3328" strokeWidth="0.6" strokeDasharray="3 4" />
            <text x={PAD.l - 6} y={g.y + 3} textAnchor="end" fontSize="9" fill="#6b7a6b" fontFamily="var(--mono)">
              {g.label}
            </text>
          </g>
        ))}
        <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={VB_H - PAD.b} stroke="#2a3328" strokeWidth="1" />
        <line x1={PAD.l} x2={VB_W - PAD.r} y1={VB_H - PAD.b} y2={VB_H - PAD.b} stroke="#2a3328" strokeWidth="1" />
        <text x={PAD.l} y={VB_H - 8} fontSize="9" fill="#6b7a6b" fontFamily="var(--mono)">BAR 0</text>
        <text x={VB_W - PAD.r} y={VB_H - 8} fontSize="9" fill="#6b7a6b" textAnchor="end" fontFamily="var(--mono)">
          BAR {pts[n - 1].i}
        </text>
        <path d={path} fill="none" stroke="var(--green)" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={xOf(0)} cy={yOf(first.v)} r="3.5" fill="var(--amber)" stroke="#0a0f0a" strokeWidth="1" />
        <circle cx={xOf(n - 1)} cy={yOf(last.v)} r="3.5" fill="var(--green)" stroke="#0a0f0a" strokeWidth="1" />
        {hover && (
          <g>
            <line x1={hover.px} x2={hover.px} y1={PAD.t} y2={VB_H - PAD.b} stroke="var(--amber)" strokeWidth="0.7" strokeDasharray="2 3" />
            <circle cx={hover.px} cy={hover.py} r="3" fill="var(--amber)" />
          </g>
        )}
      </svg>
      {hover && (
        <div
          className="mono"
          aria-live="polite"
          style={{
            position: 'absolute',
            left: `${tipLeft}%`,
            top: 34,
            transform: 'translateX(-20%)',
            background: '#0a0f0a',
            border: '1px solid var(--amber)',
            color: 'var(--text)',
            fontSize: 10,
            lineHeight: 1.55,
            padding: '5px 8px',
            pointerEvents: 'none',
            zIndex: 2,
            whiteSpace: 'nowrap',
            boxShadow: '0 0 8px rgba(255,176,0,0.25)',
          }}
        >
          <div>BAR {hover.i}</div>
          <div>DATE {hover.date != null ? hover.date : 'UNAVAILABLE'}</div>
          <div style={{ color: 'var(--green)' }}>EQUITY {fmtEq(hover.v)}</div>
        </div>
      )}
    </div>
  )
}
