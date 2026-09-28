function val(v) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'number' && isNaN(v)) return 'UNAVAILABLE'
  return v
}
function fmt(v, d = 2) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'string' && v.includes('UNAVAILABLE')) return 'UNAVAILABLE'
  if (typeof v === 'number') return v.toFixed(d)
  return String(v)
}

export default function MetricCard({ label, value, format, accent }) {
  let display
  if (value === null || value === undefined || value === '') {
    display = 'UNAVAILABLE'
  } else if (typeof value === 'string' && value.includes('UNAVAILABLE')) {
    display = 'UNAVAILABLE'
  } else if (typeof value === 'number' && isNaN(value)) {
    display = 'UNAVAILABLE'
  } else if (format === 'currency') {
    display = `₹${fmt(value, 2)}`
  } else if (format === 'percent') {
    display = `${fmt(value)}%`
  } else if (typeof format === 'number') {
    display = fmt(value, format)
  } else if (format) {
    display = `${fmt(value)}${format}`
  } else if (typeof value === 'number') {
    display = fmt(value)
  } else {
    display = val(value)
  }

  return (
    <div className="metric">
      <span>{label}</span>
      <span className={accent || ''}>{display}</span>
    </div>
  )
}
