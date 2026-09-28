import { useEffect, useState } from 'react'
import MetricCard from './components/MetricCard.jsx'
import RunHistory from './components/RunHistory.jsx'
import PipelineRail from './components/PipelineRail.jsx'

const API = ''

function val(v) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'number' && isNaN(v)) return 'UNAVAILABLE'
  return v
}
function fmt(v, d=2) {
  if (v === null || v === undefined || v === '') return 'UNAVAILABLE'
  if (typeof v === 'string' && v.includes('UNAVAILABLE')) return 'UNAVAILABLE'
  if (typeof v === 'number') return v.toFixed(d)
  return String(v)
}

export default function App() {
  const [runs, setRuns] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [audit, setAudit] = useState([])
  const [auditOpen, setAuditOpen] = useState(null)
  const [ticker, setTicker] = useState('RELIANCE')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  const fetchRuns = async () => {
    const r = await fetch(`${API}/runs`)
    const d = await r.json()
    setRuns(d)
    if (d.length && !selected) setSelected(d[0].run_id)
  }
  const fetchDetail = async (id) => {
    const r = await fetch(`${API}/runs/${id}`)
    if (!r.ok) return
    setDetail(await r.json())
    const a = await fetch(`${API}/runs/${id}/audit`)
    setAudit(a.ok ? await a.json() : [])
  }
  useEffect(()=>{fetchRuns()},[])
  useEffect(()=>{if(selected) fetchDetail(selected)},[selected])

  const createRun = async () => {
    setLoading(true); setMsg('')
    try{
      const r = await fetch(`${API}/runs`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticker})})
      const d = await r.json()
      if(!r.ok) throw new Error(d.detail||JSON.stringify(d))
      setMsg(`Created ${d.run_id} — awaiting approval`)
      await fetchRuns(); setSelected(d.run_id)
    }catch(e){setMsg('Error: '+e.message)}
    setLoading(false)
  }
  const approve = async () => {
    const r = await fetch(`${API}/runs/${selected}/approve`,{method:'POST'})
    const d = await r.json()
    if(!r.ok) setMsg('Approve failed: '+(d.detail||'')); else setMsg('Approved — paper execution authorized')
    fetchRuns(); fetchDetail(selected)
  }
  const reject = async () => {
    const r = await fetch(`${API}/runs/${selected}/reject`,{method:'POST'})
    const d = await r.json()
    if(!r.ok) setMsg('Reject failed: '+(d.detail||'')); else setMsg('Rejected — paper execution blocked')
    fetchRuns(); fetchDetail(selected)
  }

  const bt = detail?.backtest_summary
  const rk = detail?.risk_summary
  const pe = detail?.paper_execution_summary
  const approval = detail?.approval_status
  const pipeStatus = detail?.pipeline_status

  return (
    <div>
      <div className="header">
        <h1>AI EQUITY RESEARCH / RISK SIMULATION — BB-TERMINAL</h1>
        <span className="badge">PAPER TRADING ONLY — NO BROKER</span>
      </div>
      <div style={{background:'#1a1200',borderBottom:'1px solid #402a00',color:'#ffb000',fontFamily:'JetBrains Mono',fontSize:'11px',padding:'6px 16px',textAlign:'center',letterSpacing:'0.06em'}}>
        PAPER TRADING ONLY — No live broker connection — No real money — Educational / research simulation — Historical results do not guarantee future performance
      </div>
      <div className="grid">
        <div className="panel">
          <div className="card">
            <div className="card-h">NEW RUN</div>
            <label className="dim mono" style={{fontSize:10}}>TICKER</label>
            <input value={ticker} onChange={e=>setTicker(e.target.value.toUpperCase())} placeholder="RELIANCE" />
            <button className="btn" onClick={createRun} disabled={loading}>{loading?'...':'[ CREATE RUN ]'}</button>
            {msg && <div className="mono" style={{fontSize:11,marginTop:8,color:'#ffb000'}}>{msg}</div>}
          </div>
          <RunHistory runs={runs} selected={selected} onSelect={setSelected} />
        </div>

        <div className="panel">
          {!detail ? <div className="dim mono">Select a run</div> : <>
            <div className="card">
              <div className="card-h">DASHBOARD — {detail.ticker} — {detail.run_id.slice(0,8)}</div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
                <div>
                  <MetricCard label="RUN" value={detail.run_id.slice(0,12)} />
                  <MetricCard label="TICKER" value={detail.ticker} accent="amber" />
                  <MetricCard label="STRATEGY" value={bt?.strategy_type ? `${bt.strategy_type} ${bt.fast_period}/${bt.slow_period} SMA` : '—'} />
                  <MetricCard label="CAPITAL" value={bt?.initial_capital} format="currency" />
                  <MetricCard label="EQUITY" value={bt?.final_equity} format="currency" />
                </div>
                <div>
                  <MetricCard label="RETURN" value={bt?.total_return_pct} format="percent" accent="amber" />
                  <MetricCard label="TRADES" value={bt?.trade_count} />
                  <MetricCard label="MAX DD" value={bt?.max_drawdown} format="percent" />
                  <MetricCard label="APPROVAL" value={approval} />
                  <MetricCard label="EXECUTION" value={pe?.execution_status || '—'} />
                </div>
              </div>
            </div>

            <PipelineRail audit={audit} approval={approval} />

            <div className="card">
              <div className="card-h">BACKTEST — DETERMINISTIC ENGINE</div>
              <MetricCard label="Initial Capital" value={bt?.initial_capital} format="currency" />
              <MetricCard label="Final Equity" value={bt?.final_equity} format="currency" />
              <MetricCard label="Total Return" value={bt?.total_return_pct} format="percent" />
              <MetricCard label="Trades" value={bt?.trade_count} />
              <MetricCard label="Win Rate" value={bt?.win_rate!=null?bt.win_rate*100:null} format="percent" />
              <MetricCard label="Avg Win" value={bt?.avg_win} />
              <MetricCard label="Avg Loss" value={bt?.avg_loss} />
              <MetricCard label="Profit Factor" value={bt?.profit_factor} />
              <MetricCard label="Max Drawdown" value={bt?.max_drawdown} format="percent" />
              <MetricCard label="Commission" value={bt?.commission_assumption} format="percent" />
              <MetricCard label="Slippage" value={bt?.slippage_assumption} format="percent" />
              <MetricCard label="Bars" value={bt?.number_of_bars} />
              <MetricCard label="Period" value={bt?.data_start && bt?.data_end ? `${bt.data_start} → ${bt.data_end}` : null} />
            </div>

            <div className="card">
              <div className="card-h">RISK — SEBI-INFORMED SIMULATION CONTROLS</div>
              <div style={{fontSize:10,color:'#ffb000',border:'1px solid #402a00',background:'#1a1200',padding:'6px',marginBottom:8,letterSpacing:'0.04em'}}>SIMULATION CONTROL — Not SEBI compliant — Educational only</div>
              <MetricCard label="Position Size" value={rk?.position_size} format="%" />
              <MetricCard label="Stop Loss" value={rk?.stop_loss} />
              <MetricCard label="Exposure Limit" value={rk?.exposure_limit} format="%" />
              <MetricCard label="Daily Loss Limit" value={rk?.daily_loss_limit} format="%" />
              <MetricCard label="Checks Passed" value={rk?.checks_passed ? 'YES':'NO'} />
              {rk?.risk_warnings?.length>0 && <div style={{marginTop:8}}><div className="mono dim" style={{fontSize:10}}>WARNINGS</div>{rk.risk_warnings.map((w,i)=><div key={i} className="mono" style={{fontSize:11,padding:'3px 0',borderBottom:'1px solid #222'}}>{w}</div>)}</div>}
              {rk?.sebi_aligned_controls?.length>0 && <div style={{marginTop:8}}><div className="mono dim" style={{fontSize:10}}>CONTROLS</div>{rk.sebi_aligned_controls.map((c,i)=><div key={i} className="mono" style={{fontSize:11,padding:'2px 0'}}>• {c}</div>)}</div>}
            </div>
          </> }
        </div>

        <div className="panel">
          {detail && <>
            <div className="card">
              <div className="card-h">APPROVAL</div>
              <div style={{textAlign:'center',padding:'8px 0'}}>
                <div className={`badge-status ${approval==='approved'?'ok':approval==='rejected'?'bad':'warn'}`} style={{display:'inline-block',padding:'6px 12px',fontSize:12}}>
                  {approval==='pending'?'WAITING FOR APPROVAL': approval==='approved'?'APPROVED': approval==='rejected'?'REJECTED': approval}
                </div>
                <div className="mono dim" style={{fontSize:10,marginTop:6}}>{pipeStatus}</div>
              </div>
              {approval==='pending' && <>
                <button className="btn" onClick={approve}>[ APPROVE PAPER TRADE ]</button>
                <button className="btn reject" onClick={reject}>[ REJECT ]</button>
              </>}
              {approval==='rejected' && <div className="mono" style={{textAlign:'center',padding:8,border:'1px solid #ff3d00',color:'#ff3d00',marginTop:8}}>PAPER EXECUTION BLOCKED</div>}
              {approval==='approved' && <div className="mono" style={{textAlign:'center',padding:8,border:'1px solid #00c853',color:'#00c853',marginTop:8}}>PAPER EXECUTION AUTHORIZED — {pe?.trade_id?.slice(0,8)||''}</div>}
              <div className="dim mono" style={{fontSize:10,marginTop:8}}>No broker — simulated only — explicit human action required</div>
            </div>

            <div className="card">
              <div className="card-h">AUDIT TRAIL — {audit.length} records</div>
              {audit.map(a=>(
                <div key={a.id} className="timeline-item" onClick={()=>setAuditOpen(auditOpen===`a-${a.id}`?null:`a-${a.id}`)}>
                  <div className="mono" style={{fontSize:10,color:'#ffb000'}}>{a.timestamp?.slice(11,19)} — {a.agent_name}</div>
                  <div className="mono dim" style={{fontSize:10}}>{a.human_approval_status||'n/a'} {a.approved_by?`· ${a.approved_by}`:''}</div>
                  {auditOpen===`a-${a.id}` && <div className="json" style={{marginTop:6}}>{JSON.stringify({input:a.input_json, output:a.output_json}, null, 2)}</div>}
                </div>
              ))}
            </div>

            {pe && (
              <div className="card">
                <div className="card-h">PAPER EXECUTION</div>
                <MetricCard label="Trade ID" value={pe.trade_id?.slice(0,12)} />
                <MetricCard label="Status" value={pe.execution_status} />
                <MetricCard label="Type" value={pe.execution_type} />
                <MetricCard label="Qty (sim)" value={pe.simulated_quantity} />
                <div className="dim mono" style={{fontSize:10,marginTop:6}}>{pe.simulation_disclaimer?.slice(0,90)}…</div>
              </div>
            )}
          </>}
        </div>
      </div>
      <div className="dim mono" style={{textAlign:'center',padding:10,fontSize:10,borderTop:'1px solid #1a2218'}}>
        API: /health · /runs · /runs/{'{id}'}/backtest · /runs/{'{id}'}/risk · /runs/{'{id}'}/audit — React never calculates metrics — Source: deterministic Python engine — No broker integration
      </div>
    </div>
  )
}
