function fmtTs(v) {
  if (typeof v !== 'string' || !v) return null
  return v.slice(0, 19).replace('T', ' ')
}

function PRow({ label, value, tone }) {
  const color = tone === 'green' ? 'var(--green)' : tone === 'red' ? 'var(--red)' : tone === 'amber' ? 'var(--amber)' : undefined
  return (
    <div className="metric">
      <span>{label}</span>
      <span style={{ textAlign: 'right', maxWidth: '65%', ...(color ? { color } : {}) }}>{value}</span>
    </div>
  )
}

export default function DataProvenance({ rec, bt }) {
  if (!rec) return null
  const input = rec.input_json && typeof rec.input_json === 'object' ? rec.input_json : {}
  const ohlc = input.ohlc && typeof input.ohlc === 'object' ? input.ohlc : null
  const out = rec.output_json && typeof rec.output_json === 'object' ? rec.output_json : {}
  const btOut = bt && bt.output_json && typeof bt.output_json === 'object' ? bt.output_json : null

  const source = ohlc && typeof ohlc.source === 'string' && ohlc.source ? ohlc.source : null
  const symbolRaw = (ohlc && ohlc.resolved_ticker) || input.resolved_ticker || out.resolved_ticker || null
  const symbol = typeof symbolRaw === 'string' && symbolRaw ? symbolRaw : null
  const period = ohlc && typeof ohlc.period === 'string' && ohlc.period ? ohlc.period : null
  const interval = ohlc && typeof ohlc.interval === 'string' && ohlc.interval ? ohlc.interval : null
  const cachedAt = fmtTs(ohlc && ohlc.cached_at)
  const retrievedAt = fmtTs((ohlc && ohlc.retrieved_at) || input.retrieved_at)
  const bars = btOut && typeof btOut.number_of_bars === 'number' && isFinite(btOut.number_of_bars) ? btOut.number_of_bars : null
  const isMock = btOut && typeof btOut.is_mock === 'boolean' ? btOut.is_mock : null

  // data/fetch.py is the sole market-data layer: it fetches via yfinance and writes its
  // Parquet cache only from yfinance results, so both known source values map to that provider.
  const knownSource = source === 'cache' || source === 'yahoo_finance'
  const sourceLabel = source ? (knownSource ? 'Yahoo Finance / yfinance' : source) : null
  const cacheValue = source === 'cache' ? { value: 'HIT', tone: 'green' }
    : source === 'yahoo_finance' ? { value: 'MISS (FETCHED)', tone: 'amber' }
    : null
  const dataType = (period || interval)
    ? `Historical OHLCV (${[period, interval].filter(Boolean).join('/')})`
    : 'Historical OHLCV'

  const hasAny = Boolean(sourceLabel || symbol || cachedAt || retrievedAt || bars !== null || isMock !== null)
  return (
    <div>
      <div style={{ color: 'var(--amber)', fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: '0.08em', marginTop: 10 }}>DATA PROVENANCE</div>
      <div style={{ borderTop: '1px solid var(--border)', margin: '3px 0 2px' }} />
      {!hasAny && <PRow label="PROVENANCE" value="DATA UNAVAILABLE" />}
      {sourceLabel && <PRow label="SOURCE" value={sourceLabel} />}
      {symbol && <PRow label="SYMBOL" value={symbol} />}
      {ohlc && <PRow label="DATA TYPE" value={dataType} />}
      {bars !== null && <PRow label="BARS" value={bars} />}
      {cacheValue && <PRow label="CACHE" value={cacheValue.value} tone={cacheValue.tone} />}
      {cachedAt && <PRow label="CACHED AT" value={cachedAt} />}
      {retrievedAt && <PRow label="RETRIEVED" value={retrievedAt} />}
      {isMock !== null && (
        <PRow label="MODE" value={isMock ? 'MOCK DATA' : 'REAL DATA'} tone={isMock ? 'red' : 'green'} />
      )}
    </div>
  )
}
