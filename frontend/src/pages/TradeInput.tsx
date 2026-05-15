import { useEffect, useMemo, useState } from 'react'
import { Card, SectionHeader } from '../components/Card'
import { MONTHS } from '../lib/utils'

interface Section { name: string; stocks: { name: string; realized: boolean }[] }
interface Settings { sections: Section[] }
type TradeSide = 'profit' | 'loss'
type ApiErrorDetail = { detail?: string | { msg?: string }[] }

interface Props { onDataUpdate?: () => void }

export default function TradeInput({ onDataUpdate }: Props) {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState(MONTHS[new Date().getMonth()])
  const [stockNames, setStockNames] = useState<Record<string, string>>({})
  const [amounts, setAmounts] = useState<Record<string, string>>({})
  const [sides, setSides] = useState<Record<string, TradeSide>>({})
  const [messages, setMessages] = useState<Record<string, { type: 'ok' | 'err'; text: string }>>({})

  const YEARS = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i)

  useEffect(() => {
    fetch('/api/settings').then(r => r.json()).then(setSettings)
  }, [])

  const sections = useMemo(() => {
    const list = settings?.sections ?? []
    return [...list].sort((a, b) => {
      const rank = (name: string) => name.includes('미국') ? 0 : name.includes('국내') ? 1 : 2
      return rank(a.name) - rank(b.name)
    })
  }, [settings])

  const parseError = (d: ApiErrorDetail | null, fallback: string): string => {
    if (!d) return fallback
    if (typeof d.detail === 'string') return d.detail
    if (Array.isArray(d.detail)) return d.detail.map(e => e.msg ?? JSON.stringify(e)).join(', ')
    return fallback
  }

  const updateMessage = (sectionName: string, message: { type: 'ok' | 'err'; text: string }) => {
    setMessages(prev => ({ ...prev, [sectionName]: message }))
  }

  const handleTrade = async (e: React.FormEvent, section: Section) => {
    e.preventDefault()

    const stockName = (stockNames[section.name] ?? '').trim()
    if (!stockName) {
      updateMessage(section.name, { type: 'err', text: '종목명을 입력하세요.' })
      return
    }

    const rawAmount = amounts[section.name] ?? ''
    const parsedAmount = Number(rawAmount)
    if (rawAmount.trim() === '' || !Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      updateMessage(section.name, { type: 'err', text: '금액은 0보다 큰 숫자로 입력하세요.' })
      return
    }

    const side = sides[section.name] ?? 'profit'
    const signedAmount = side === 'loss' ? -Math.abs(parsedAmount) : Math.abs(parsedAmount)
    const res = await fetch('/api/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section_name: section.name,
        year,
        month,
        stock_name: stockName,
        amount: signedAmount,
        realized: true,
      }),
    })

    if (res.ok) {
      updateMessage(section.name, {
        type: 'ok',
        text: `${month} / ${stockName} ${side === 'profit' ? '수익' : '손실'} 저장 완료`,
      })
      setStockNames(prev => ({ ...prev, [section.name]: '' }))
      setAmounts(prev => ({ ...prev, [section.name]: '' }))
      fetch('/api/settings').then(r => r.json()).then(setSettings)
      onDataUpdate?.()
    } else {
      const d = await res.json()
      updateMessage(section.name, { type: 'err', text: parseError(d, '저장 실패') })
    }
  }

  const inputCls = 'w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white'
  const selectCls = inputCls

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">매매 입력</h1>
        <p className="text-sm text-slate-400 mt-1">실현손익을 시장별로 빠르게 기록합니다.</p>
      </div>

      <Card className="p-5 max-w-2xl">
        <SectionHeader title="입력 기준" />
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">연도</label>
            <select className={selectCls} value={year} onChange={e => setYear(Number(e.target.value))}>
              {YEARS.map(y => <option key={y} value={y}>{y}년</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-500 mb-1 block">월</label>
            <select className={selectCls} value={month} onChange={e => setMonth(e.target.value)}>
              {MONTHS.map(m => <option key={m}>{m}</option>)}
            </select>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {sections.map(section => {
          const side = sides[section.name] ?? 'profit'
          const message = messages[section.name]
          const datalistId = `stock-suggestions-${section.name}`

          return (
            <Card key={section.name} className="p-5">
              <SectionHeader title={section.name} />
              <form onSubmit={e => handleTrade(e, section)} className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-slate-500 mb-1 block">종목명</label>
                  <input
                    className={inputCls}
                    placeholder={section.name.includes('미국') ? '예: TQQQ' : '예: 삼성전자'}
                    value={stockNames[section.name] ?? ''}
                    onChange={e => setStockNames(prev => ({ ...prev, [section.name]: e.target.value }))}
                    list={datalistId}
                  />
                  <datalist id={datalistId}>
                    {section.stocks.map(s => <option key={s.name} value={s.name} />)}
                  </datalist>
                </div>

                <div>
                  <label className="text-xs font-medium text-slate-500 mb-1 block">구분</label>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setSides(prev => ({ ...prev, [section.name]: 'profit' }))}
                      className={`py-2.5 rounded-lg text-sm font-semibold border transition-colors ${
                        side === 'profit'
                          ? 'bg-red-50 text-red-600 border-red-200'
                          : 'bg-white text-slate-500 border-slate-200 hover:border-red-200'
                      }`}
                    >
                      수익
                    </button>
                    <button
                      type="button"
                      onClick={() => setSides(prev => ({ ...prev, [section.name]: 'loss' }))}
                      className={`py-2.5 rounded-lg text-sm font-semibold border transition-colors ${
                        side === 'loss'
                          ? 'bg-blue-50 text-blue-600 border-blue-200'
                          : 'bg-white text-slate-500 border-slate-200 hover:border-blue-200'
                      }`}
                    >
                      손실
                    </button>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-slate-500 mb-1 block">
                    금액 {section.name.includes('미국') ? '(USD)' : '(KRW)'}
                  </label>
                  <input
                    type="number"
                    min="0"
                    className={inputCls}
                    value={amounts[section.name] ?? ''}
                    onChange={e => setAmounts(prev => ({ ...prev, [section.name]: e.target.value }))}
                    step="any"
                    placeholder={side === 'profit' ? '수익 금액' : '손실 금액'}
                  />
                </div>

                <button
                  type="submit"
                  className={`w-full text-white font-medium py-2.5 rounded-lg text-sm transition-colors ${
                    side === 'profit' ? 'bg-red-500 hover:bg-red-600' : 'bg-blue-500 hover:bg-blue-600'
                  }`}
                >
                  {side === 'profit' ? '수익 저장' : '손실 저장'}
                </button>

                {message && (
                  <p className={`text-xs rounded-lg px-3 py-2 ${message.type === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                    {message.text}
                  </p>
                )}
              </form>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
