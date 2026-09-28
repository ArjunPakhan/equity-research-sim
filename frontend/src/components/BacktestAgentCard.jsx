import { useState } from 'react'
import EquityCurveChart from './EquityCurveChart'
import DrawdownChart from './DrawdownChart'
import PriceStrategyChart from './PriceStrategyChart'

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
function row(label, value) {
  return (
    <div className="metric">
      <span>{label}</span>
      <span style={{ textAlign: 'right', maxWidth: '65%' }}>{value}</span>
    </div>
  )
}

export default function BacktestAgentCard({ rec, ohlc }) {
  const [showRaw, setShowRaw] = useState(false)
  if (!rec) return null
  const o = rec.output_json || {}
  const strategy = o.strategy_type
    ? `${o.strategy_type}${o.fast_period != null && o.slow_period != null ? ` ${o.fast_period}/${o.slow_period} SMA` : ''}`
    : null
  const strategyLabel = o.fast_period != null && o.slow_period != null ? `${o.fast_period}/${o.slow_period} SMA` : o.strategy_type || null
  const ticker = o.resolved_ticker || o.ticker || null
  const period = o.data_start && o.data_end ? `${o.data_start} → ${o.data_end}` : null
  const winRate = typeof o.win_rate === 'number' ? o.win_rate * 100 : o.win_rate
  const dd = typeof o.max_drawdown === 'number' ? o.max_drawdown : o.max_drawdown
  const commission = typeof o.commission_assumption === 'number' ? o.commission_assumption : o.commission_assumption
  const slippage = typeof o.slippage_assumption === 'number' ? o.slippage_assumption : o.slippage_assumption

  return (
    <div className="card" style={{ marginTop: 8 }}>
      <div className="card-h">DETERMINISTIC BACKTEST ENGINE</div>
      <div className="mono" style={{ fontSize: 10, letterSpacing: '0.06em', color: 'var(--amber)', border: '1px solid #402a00', background: '#1a1200', padding: '5px 7px', marginBottom: 8 }}>
        PYTHON ENGINE — NOT LLM — DETERMINISTIC VALUES ONLY
      </div>
      {row('STATUS', rec.human_approval_status === 'approved' ? 'COMPLETED (APPROVED)' : 'COMPLETED')}
      {row('TIMESTAMP', rec.timestamp ? String(rec.timestamp).slice(0, 19).replace('T', ' ') : null)}
      {row('STRATEGY', val(strategy))}
      {row('INITIAL CAPITAL', `₹${fmt(o.initial_capital)}`)}
      {row('FINAL EQUITY', `₹${fmt(o.final_equity)}`)}
      {row('TOTAL RETURN', `${fmt(o.total_return_pct)}%`)}
      {row('TRADES', fmt(o.trade_count, 0))}
      {row('WIN RATE', typeof winRate === 'string' ? val(winRate) : `${fmt(winRate)}%`)}
      {row('AVG WIN', fmt(o.avg_win))}
      {row('AVG LOSS', fmt(o.avg_loss))}
      {row('PROFIT FACTOR', fmt(o.profit_factor))}
      {row('MAX DRAWDOWN', typeof dd === 'string' ? val(dd) : `${fmt(dd)}%`)}
      {row('COMMISSION', `${fmt(commission)}%`)}
      {row('SLIPPAGE', `${fmt(slippage)}%`)}
      {row('BARS', fmt(o.number_of_bars, 0))}
      {row('PERIOD', val(period))}
      {o.data_status ? row('DATA STATUS', val(o.data_status)) : null}
      <PriceStrategyChart ohlc={ohlc} barDates={o.bar_dates} trades={o.trades} ticker={ticker} strategyLabel={strategyLabel} />
      <EquityCurveChart equityCurve={o.equity_curve} barDates={o.bar_dates} />
      <DrawdownChart drawdownSeries={o.drawdown_series} barDates={o.bar_dates} />
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
