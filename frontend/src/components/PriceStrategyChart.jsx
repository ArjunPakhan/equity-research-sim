import { useMemo, useRef, useState } from 'react'

const VB_W = 640
const VB_H = 260
const PAD = { t: 18, r: 16, b: 30, l: 56 }

function isNum(v) {
  return typeof v === 'number' && Number.isFinite(v)
}

function finiteOr(v) {
  return isNum(v) ? v : null
}

function fmtInr(v) {
  if (!isNum(v)) return 'UNAVAILABLE'
  return `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(v) {
  if (!isNum(v)) return 'UNAVAILABLE'
  return `${v.toFixed(2)}%`
}

function fmtDate(barDates, i) {
  if (Array.isArray(barDates) && barDates[i] != null && barDates[i] !== '') {
    return String(barDates[i]).slice(0, 10)
  }
  return 'UNAVAILABLE'
}

function shortAxisDate(s) {
  if (!s) return ''
  const t = String(s)
  if (/^\d{4}-\d{2}-\d{2}/.test(t)) {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const m = parseInt(t.slice(5, 7), 10) - 1
    return `${months[m] ?? t.slice(5, 7)} ${t.slice(8, 10)}`
  }
  return t.slice(0, 10)
}

/** Align audit OHLC rows to finite price bars (drops null/NaN closes). Bar index = position. */
function normalizeOhlc(ohlc) {
  if (!Array.isArray(ohlc) || ohlc.length === 0) return null
  const bars = []
  for (let i = 0; i < ohlc.length; i++) {
    const r = ohlc[i]
    if (!r || typeof r !== 'object') continue
    const c = finiteOr(r.Close ?? r.close)
    if (c === null) continue
    bars.push({
      o: finiteOr(r.Open ?? r.open),
      h: finiteOr(r.High ?? r.high),
      l: finiteOr(r.Low ?? r.low),
      c,
      date: r.Date != null ? String(r.Date) : null,
    })
  }
  return bars.length > 0 ? bars : null
}

function axisTicks(yMin, yMax, count = 4) {
  const out = []
  if (!isNum(yMin) || !isNum(yMax) || yMax <= yMin) return out
  for (let i = 0; i <= count; i++) {
    const v = yMin + ((yMax - yMin) * i) / count
    out.push(v)
  }
  return out
}

function nicePrice(v) {
  if (!isNum(v)) return ''
  if (Math.abs(v) >= 1000) return `₹${v.toFixed(0)}`
  return `₹${v.toFixed(1)}`
}

export default function PriceStrategyChart({ ohlc, barDates, trades, ticker, strategyLabel }) {
  const svgRef = useRef(null)
  const [hoverBar, setHoverBar] = useState(null)
  const [focusMarker, setFocusMarker] = useState(null)

  const bars = useMemo(() => normalizeOhlc(ohlc), [ohlc])
  const tradeList = useMemo(() => (Array.isArray(trades) ? trades.filter((t) => t && typeof t === 'object') : []), [trades])

  const markers = useMemo(() => {
    if (!bars || tradeList.length === 0) return []
    const out = []
    for (const t of tradeList) {
      const id = t.trade_id
      const et = t.entry_time
      const xt = t.exit_time
      if (isNum(et) && et >= 0 && et < bars.length) {
        out.push({ key: `b-${id}`, side: 'BUY', bar: et, price: t.entry_price, trade: t })
      }
      if (isNum(xt) && xt >= 0 && xt < bars.length) {
        out.push({ key: `s-${id}`, side: 'SELL', bar: xt, price: t.exit_price, trade: t })
      }
    }
    return out
  }, [bars, tradeList])

  const title = `${ticker || 'ASSET'} — PRICE / STRATEGY`
  const subtitle = strategyLabel || null

  if (!bars) {
    return (
      <div className="card" style={{ marginTop: 8, padding: '10px 12px' }} role="img" aria-label="Price strategy chart data unavailable">
        <div className="card-h" style={{ marginBottom: 6 }}>{title}</div>
        <div className="mono" style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.08em' }}>DATA UNAVAILABLE</div>
      </div>
    )
  }

  const n = bars.length
  let yMin = Infinity
  let yMax = -Infinity
  for (const b of bars) {
    const lo = b.l != null ? b.l : b.c
    const hi = b.h != null ? b.h : b.c
    if (isNum(lo) && lo < yMin) yMin = lo
    if (isNum(hi) && hi > yMax) yMax = hi
  }
  for (const m of markers) {
    if (isNum(m.price)) {
      if (m.price < yMin) yMin = m.price
      if (m.price > yMax) yMax = m.price
    }
  }
  if (!isNum(yMin) || !isNum(yMax)) {
    return (
      <div className="card" style={{ marginTop: 8, padding: '10px 12px' }} role="img" aria-label="Price strategy chart data unavailable">
        <div className="card-h" style={{ marginBottom: 6 }}>{title}</div>
        <div className="mono" style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.08em' }}>DATA UNAVAILABLE</div>
      </div>
    )
  }
  if (yMax === yMin) {
    yMin -= 1
    yMax += 1
  }
  const padY = (yMax - yMin) * 0.08
  yMin -= padY
  yMax += padY

  const plotW = VB_W - PAD.l - PAD.r
  const plotH = VB_H - PAD.t - PAD.b
  const xOf = (bar) => PAD.l + (n === 1 ? plotW / 2 : (bar / (n - 1)) * plotW)
  const yOf = (v) => PAD.t + (1 - (v - yMin) / (yMax - yMin)) * plotH

  const useCandles = n <= 320
  const bodyW = Math.max(1, Math.min(6, (plotW / n) * 0.65))

  const closePath = bars
    .map((b, i) => `${i === 0 ? 'M' : 'L'}${xOf(i).toFixed(2)},${yOf(b.c).toFixed(2)}`)
    .join(' ')

  const ticks = axisTicks(yMin, yMax, 4)
  const xLabelBars = [0, Math.floor((n - 1) / 2), n - 1]

  const onMove = (e) => {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * VB_W
    const t = Math.min(1, Math.max(0, (x - PAD.l) / plotW))
    const bar = Math.round(t * (n - 1))
    setHoverBar(bar)
    setFocusMarker(null)
  }

  const tipBar = focusMarker != null ? focusMarker.bar : hoverBar
  const tipMarker = focusMarker

  const tipLeftPct = tipBar != null ? Math.min(Math.max((xOf(tipBar) / VB_W) * 100, 6), 70) : 0

  function markerTipLines(m) {
    const t = m.trade
    const lines = [
      `TRADE #${t.trade_id ?? '—'}`,
      m.side,
      `BAR ${m.bar}`,
      `DATE ${fmtDate(barDates, m.bar)}`,
      `PRICE ${fmtInr(m.price)}`,
    ]
    if (m.side === 'SELL') {
      lines.push(`NET P&L ${isNum(t.net_pnl) ? `${t.net_pnl < 0 ? '-' : ''}₹${Math.abs(t.net_pnl).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : 'UNAVAILABLE'}`)
      lines.push(`RETURN ${fmtPct(t.return_pct)}`)
      if (isNum(t.fees)) lines.push(`FEES ₹${t.fees.toFixed(2)}`)
      if (isNum(t.slippage)) lines.push(`SLIPPAGE ₹${t.slippage.toFixed(2)}`)
      if (t.status != null) lines.push(`STATUS ${String(t.status).toUpperCase()}`)
      if (isNum(t.entry_price)) lines.push(`ENTRY ${fmtInr(t.entry_price)}`)
      if (isNum(t.exit_price)) lines.push(`EXIT ${fmtInr(t.exit_price)}`)
    }
    return lines
  }

  function barTipLines(bar) {
    const b = bars[bar]
    if (!b) return []
    const lines = [`BAR ${bar}`, `DATE ${barDates?.[bar] != null ? String(barDates[bar]).slice(0, 19).replace('T', ' ') : fmtDate(bars.map((x) => x.date), bar)}`]
    if (b.o != null) lines.push(`O ${nicePrice(b.o)}`)
    if (b.h != null) lines.push(`H ${nicePrice(b.h)}`)
    if (b.l != null) lines.push(`L ${nicePrice(b.l)}`)
    lines.push(`C ${nicePrice(b.c)}`)
    return lines
  }

  const tipLines = tipMarker ? markerTipLines(tipMarker) : tipBar != null ? barTipLines(tipBar) : []

  return (
    <div className="card" style={{ marginTop: 8, padding: '10px 12px', position: 'relative', overflow: 'hidden' }}>
      <div className="card-h" style={{ marginBottom: 4, display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
        <span>{title}</span>
        <span style={{ color: 'var(--muted)' }}>{subtitle}</span>
      </div>
      <div className="mono" style={{ fontSize: 9, color: 'var(--muted)', letterSpacing: '0.06em', marginBottom: 6 }}>
        {useCandles ? 'OHLC CANDLES' : 'CLOSE LINE'} · BUY ▲ / SELL ▼ · BAR INDEX → bar_dates
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        width="100%"
        height="auto"
        style={{ display: 'block', maxHeight: 280, overflow: 'visible' }}
        role="img"
        aria-label={`${title}. ${n} price bars. ${markers.filter((m) => m.side === 'BUY').length} buy and ${markers.filter((m) => m.side === 'SELL').length} sell markers from deterministic backtest trades.`}
        onMouseMove={onMove}
        onMouseLeave={() => {
          setHoverBar(null)
          setFocusMarker(null)
        }}
      >
        <title>{title}</title>
        <desc>
          Price chart with backend OHLC data and trade entry/exit markers. Buy markers use triangle up; sell markers use triangle down.
        </desc>

        {ticks.map((v) => (
          <g key={`ty-${v}`}>
            <line x1={PAD.l} x2={VB_W - PAD.r} y1={yOf(v)} y2={yOf(v)} stroke="#2a3328" strokeWidth="0.6" strokeDasharray="3 4" />
            <text x={PAD.l - 6} y={yOf(v) + 3} textAnchor="end" fontSize="9" fill="#6b7a6b" fontFamily="var(--mono)">
              {nicePrice(v)}
            </text>
          </g>
        ))}
        <line x1={PAD.l} x2={PAD.l} y1={PAD.t} y2={VB_H - PAD.b} stroke="#2a3328" strokeWidth="1" />
        <line x1={PAD.l} x2={VB_W - PAD.r} y1={VB_H - PAD.b} y2={VB_H - PAD.b} stroke="#2a3328" strokeWidth="1" />

        {xLabelBars.map((bar) => (
          <text
            key={`tx-${bar}`}
            x={xOf(bar)}
            y={VB_H - 8}
            fontSize="9"
            fill="#6b7a6b"
            textAnchor={bar === 0 ? 'start' : bar === n - 1 ? 'end' : 'middle'}
            fontFamily="var(--mono)"
          >
            {shortAxisDate(barDates?.[bar] || bars[bar]?.date)}
          </text>
        ))}

        {useCandles ? (
          bars.map((b, i) => {
            const x = xOf(i)
            const up = b.o != null ? b.c >= b.o : true
            const stroke = up ? 'var(--green)' : 'var(--red)'
            const openY = b.o != null ? yOf(b.o) : yOf(b.c)
            const closeY = yOf(b.c)
            const bodyTop = Math.min(openY, closeY)
            const bodyH = Math.max(1, Math.abs(closeY - openY))
            const hi = b.h != null ? b.h : Math.max(b.c, b.o ?? b.c)
            const lo = b.l != null ? b.l : Math.min(b.c, b.o ?? b.c)
            return (
              <g key={`c-${i}`}>
                <line x1={x} x2={x} y1={yOf(hi)} y2={yOf(lo)} stroke={stroke} strokeWidth="0.8" />
                <rect x={x - bodyW / 2} y={bodyTop} width={bodyW} height={bodyH} fill={up ? 'rgba(0,200,83,0.35)' : 'rgba(255,61,0,0.35)'} stroke={stroke} strokeWidth="0.7" />
              </g>
            )
          })
        ) : (
          <path d={closePath} fill="none" stroke="var(--amber)" strokeWidth="1.4" strokeLinejoin="round" />
        )}

        {!useCandles && bars.length > 0 && (
          <circle cx={xOf(0)} cy={yOf(bars[0].c)} r="3" fill="var(--amber)" />
        )}
        {!useCandles && bars.length > 1 && (
          <circle cx={xOf(n - 1)} cy={yOf(bars[n - 1].c)} r="3" fill="var(--green)" />
        )}

        {hoverBar != null && !focusMarker && (
          <line x1={xOf(hoverBar)} x2={xOf(hoverBar)} y1={PAD.t} y2={VB_H - PAD.b} stroke="var(--amber)" strokeWidth="0.7" strokeDasharray="2 3" />
        )}
        {focusMarker && (
          <line x1={xOf(focusMarker.bar)} x2={xOf(focusMarker.bar)} y1={PAD.t} y2={VB_H - PAD.b} stroke="var(--amber)" strokeWidth="0.7" strokeDasharray="2 3" />
        )}

        {markers.map((m) => {
          const x = xOf(m.bar)
          const base = isNum(m.price) ? m.price : bars[m.bar]?.c
          if (!isNum(base)) return null
          const y = yOf(base)
          const isBuy = m.side === 'BUY'
          const active = focusMarker && focusMarker.key === m.key
          const tipY = isBuy ? y + 14 : y - 14
          const tri = isBuy
            ? `${x},${y + 4} ${x - 5},${y + 13} ${x + 5},${y + 13}`
            : `${x},${y - 4} ${x - 5},${y - 13} ${x + 5},${y - 13}`
          const stemY1 = isBuy ? y + 13 : y - 13
          const stemY2 = isBuy ? y + 20 : y - 20
          return (
            <g key={m.key}>
              <line x1={x} x2={x} y1={y} y2={stemY2} stroke={isBuy ? 'var(--green)' : 'var(--red)'} strokeWidth="1" />
              <polygon
                points={tri}
                fill={isBuy ? 'var(--green)' : 'var(--red)'}
                stroke="#0a0f0a"
                strokeWidth="0.8"
              />
              <text x={x} y={tipY + (isBuy ? 8 : 0)} textAnchor="middle" fontSize="8" fill={isBuy ? 'var(--green)' : 'var(--red)'} fontFamily="var(--mono)" fontWeight="700">
                {isBuy ? 'B' : 'S'}
              </text>
              <circle
                cx={x}
                cy={y}
                r={active ? 5 : 4}
                fill={isBuy ? 'var(--green)' : 'var(--red)'}
                stroke={active ? 'var(--amber)' : '#0a0f0a'}
                strokeWidth={active ? 1.5 : 1}
                tabIndex={0}
                role="button"
                aria-label={`Trade ${m.trade.trade_id} ${m.side} bar ${m.bar} date ${fmtDate(barDates, m.bar)} price ${fmtInr(m.price)}`}
                style={{ cursor: 'pointer', outline: 'none' }}
                onFocus={() => {
                  setFocusMarker(m)
                  setHoverBar(null)
                }}
                onBlur={() => setFocusMarker(null)}
                onMouseEnter={() => {
                  setFocusMarker(m)
                  setHoverBar(null)
                }}
                onMouseLeave={() => setFocusMarker(null)}
              />
            </g>
          )
        })}
      </svg>

      {tipLines.length > 0 && (
        <div
          className="mono"
          aria-live="polite"
          style={{
            position: 'absolute',
            left: `${tipLeftPct}%`,
            top: 52,
            transform: 'translateX(-15%)',
            background: '#0a0f0a',
            border: `1px solid ${tipMarker ? (tipMarker.side === 'BUY' ? 'var(--green)' : 'var(--red)') : 'var(--amber)'}`,
            color: 'var(--text)',
            fontSize: 10,
            lineHeight: 1.55,
            padding: '5px 8px',
            pointerEvents: 'none',
            zIndex: 2,
            whiteSpace: 'nowrap',
            boxShadow: tipMarker ? 'none' : '0 0 6px rgba(255,176,0,0.2)',
            transition: 'opacity 125ms cubic-bezier(0.23, 1, 0.32, 1)',
          }}
        >
          {tipLines.map((line, i) => (
            <div
              key={i}
              style={{
                color: i === 0 ? 'var(--amber)' : tipMarker && line.startsWith('BUY') ? 'var(--green)' : tipMarker && (line.startsWith('SELL') || line.startsWith('NET') || line.startsWith('RETURN -')) ? 'var(--red)' : undefined,
              }}
            >
              {line}
            </div>
          ))}
        </div>
      )}

      <div className="mono" style={{ fontSize: 9, color: 'var(--muted)', marginTop: 6, letterSpacing: '0.04em' }}>
        SOURCE: research audit OHLC · backtest trades (entry_time/exit_time = integer bar indexes) · no React financial math
      </div>
      <style>{`
        svg circle[role="button"]:focus-visible { outline: 1px solid var(--amber); outline-offset: 2px; }
        @media (prefers-reduced-motion: reduce) { .mono[aria-live] { transition: none !important; } }
      `}</style>
    </div>
  )
}
