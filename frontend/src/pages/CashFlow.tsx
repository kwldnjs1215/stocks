import { useEffect, useState } from 'react'
import { Card, KpiCard, SectionHeader } from '../components/Card'
import { fmtKrw, colorClass } from '../lib/utils'

interface CashFlow { date: string; type: string; amount: number; memo: string }
interface Settings { baseline_principal_krw: number; cash_flows: CashFlow[] }

function calcPrincipal(s: Settings): number {
  let total = s.baseline_principal_krw
  for (const f of s.cash_flows) {
    if (f.type === '입금') total += f.amount
    else if (f.type === '출금') total -= f.amount
  }
  return total
}

interface Props { onDataUpdate?: () => void }

export default function CashFlow({ onDataUpdate }: Props) {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [type, setType] = useState<'입금' | '출금'>('입금')
  const [amount, setAmount] = useState(0)
  const [memo, setMemo] = useState('')
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  const load = () => fetch('/api/settings').then(r => r.json()).then(setSettings)
  useEffect(() => { load() }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (amount <= 0) { setMsg({ type: 'err', text: '금액은 0보다 크게 입력하세요.' }); return }
    const res = await fetch('/api/cashflows', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, type, amount, memo }),
    })
    if (res.ok) {
      setMsg({ type: 'ok', text: '입출금 내역을 저장했습니다.' })
      setAmount(0); setMemo('')
      load()
      onDataUpdate?.()
    } else {
      setMsg({ type: 'err', text: '저장 실패' })
    }
  }

  const inputCls = 'w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white'

  if (!settings) return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
    </div>
  )

  const current = calcPrincipal(settings)
  const baseline = settings.baseline_principal_krw
  const delta = current - baseline

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">입출금 관리</h1>
        <p className="text-sm text-slate-400 mt-1">원금 변동 추적</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <KpiCard label="기준 원금" value={fmtKrw(baseline)} />
        <KpiCard label="수동 반영 증감" value={fmtKrw(delta)} valueClass={colorClass(delta)} />
        <KpiCard label="현재 원금" value={fmtKrw(current)} valueClass="text-blue-600" />
      </div>

      <Card className="p-5 max-w-sm">
        <SectionHeader title="입출금 추가" />
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">날짜</label>
            <input type="date" className={inputCls} value={date} onChange={e => setDate(e.target.value)} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">유형</label>
            <div className="flex gap-2">
              {(['입금', '출금'] as const).map(t => (
                <button key={t} type="button"
                  onClick={() => setType(t)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all ${
                    type === t
                      ? t === '입금' ? 'bg-red-500 text-white' : 'bg-blue-500 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">금액</label>
            <input type="number" className={inputCls} value={amount}
              onChange={e => setAmount(Number(e.target.value))} min={0} step={10000} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">메모</label>
            <input className={inputCls} placeholder="예: 추가 입금, 생활비 출금"
              value={memo} onChange={e => setMemo(e.target.value)} />
          </div>
          <button type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg text-sm transition-colors">
            저장
          </button>
          {msg && (
            <p className={`text-xs rounded-lg px-3 py-2 ${msg.type === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
              {msg.text}
            </p>
          )}
        </form>
      </Card>

      {settings.cash_flows.length > 0 && (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                {['날짜', '유형', '금액', '메모'].map(h => (
                  <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...settings.cash_flows].reverse().map((f, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                  <td className="px-4 py-2.5 text-slate-600">{f.date}</td>
                  <td className="px-4 py-2.5">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      f.type === '입금' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'
                    }`}>{f.type}</span>
                  </td>
                  <td className={`px-4 py-2.5 font-medium ${f.type === '입금' ? 'text-red-500' : 'text-blue-500'}`}>
                    {f.type === '입금' ? '+' : '-'}{f.amount.toLocaleString('ko-KR')}원
                  </td>
                  <td className="px-4 py-2.5 text-slate-500">{f.memo || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
