import { useEffect, useState } from 'react'
import { Card, SectionHeader } from '../components/Card'
import { MONTHS } from '../lib/utils'

interface Section { name: string; stocks: { name: string; realized: boolean }[] }
interface Settings { sections: Section[] }

interface Props { onDataUpdate?: () => void }

export default function TradeInput({ onDataUpdate }: Props) {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [sectionName, setSectionName] = useState('')
  const [year, setYear] = useState(new Date().getFullYear())
  const [month, setMonth] = useState(MONTHS[new Date().getMonth()])
  const [stockName, setStockName] = useState('')
  const [amount, setAmount] = useState(0)
  const [realized, setRealized] = useState(false)

  const YEARS = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i)
  const [newStock, setNewStock] = useState('')
  const [newRealized, setNewRealized] = useState(false)
  const [addSectionName, setAddSectionName] = useState('')
  const [msg, setMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)
  const [addMsg, setAddMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  useEffect(() => {
    fetch('/api/settings').then(r => r.json()).then(d => {
      setSettings(d)
      if (d.sections?.length) {
        setSectionName(d.sections[0].name)
        setAddSectionName(d.sections[0].name)
      }
    })
  }, [])

  // FastAPI 에러 detail이 배열일 수 있으므로 문자열로 변환
  const parseError = (d: any, fallback: string): string => {
    if (!d) return fallback
    if (typeof d.detail === 'string') return d.detail
    if (Array.isArray(d.detail)) return d.detail.map((e: any) => e.msg ?? JSON.stringify(e)).join(', ')
    return fallback
  }

  const handleTrade = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!stockName.trim()) { setMsg({ type: 'err', text: '종목명을 입력하세요.' }); return }
    const safeAmount = isNaN(amount) ? 0 : amount
    const res = await fetch('/api/trades', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section_name: sectionName, year, month, stock_name: stockName.trim(), amount: safeAmount, realized }),
    })
    if (res.ok) {
      setMsg({ type: 'ok', text: `${month} / ${stockName} 수익을 저장했습니다.` })
      setStockName(''); setAmount(0)
      onDataUpdate?.()
    } else {
      const d = await res.json()
      setMsg({ type: 'err', text: parseError(d, '저장 실패') })
    }
  }

  const handleAddStock = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newStock.trim()) { setAddMsg({ type: 'err', text: '종목명을 입력하세요.' }); return }
    const res = await fetch('/api/stocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section_name: addSectionName, stock_name: newStock.trim(), realized: newRealized }),
    })
    if (res.ok) {
      setAddMsg({ type: 'ok', text: `${addSectionName}에 ${newStock.trim()} 추가 완료` })
      setNewStock('')
      fetch('/api/settings').then(r => r.json()).then(setSettings)
      onDataUpdate?.()
    } else {
      const d = await res.json()
      setAddMsg({ type: 'err', text: parseError(d, '추가 실패') })
    }
  }

  const sections = settings?.sections ?? []
  const currentSection = sections.find(s => s.name === sectionName)

  const inputCls = 'w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white'
  const selectCls = inputCls

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">매매 입력</h1>
        <p className="text-sm text-slate-400 mt-1">월별 수익 기록 및 종목 추가</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* 수익 입력 */}
        <Card className="p-5">
          <SectionHeader title="수익 반영" />
          <form onSubmit={handleTrade} className="space-y-3">
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">시장</label>
              <select className={selectCls} value={sectionName} onChange={e => setSectionName(e.target.value)}>
                {sections.map(s => <option key={s.name}>{s.name}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
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
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">종목명</label>
              <input
                className={inputCls} placeholder="예: 삼성전자, TQQQ"
                value={stockName} onChange={e => setStockName(e.target.value)}
                list="stock-suggestions"
              />
              <datalist id="stock-suggestions">
                {currentSection?.stocks.map(s => <option key={s.name} value={s.name} />)}
              </datalist>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">수익 금액</label>
              <input type="number" className={inputCls} value={amount} onChange={e => { const v = Number(e.target.value); setAmount(isNaN(v) ? 0 : v) }} step="any" />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
              <input type="checkbox" checked={realized} onChange={e => setRealized(e.target.checked)}
                className="w-4 h-4 rounded accent-blue-600" />
              실현 종목으로 표시
            </label>
            <button type="submit"
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg text-sm transition-colors">
              수익 저장
            </button>
            {msg && (
              <p className={`text-xs rounded-lg px-3 py-2 ${msg.type === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                {msg.text}
              </p>
            )}
          </form>
        </Card>

        {/* 종목 추가 */}
        <Card className="p-5">
          <SectionHeader title="종목 추가" />
          <form onSubmit={handleAddStock} className="space-y-3">
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">시장</label>
              <select className={selectCls} value={addSectionName} onChange={e => setAddSectionName(e.target.value)}>
                {sections.map(s => <option key={s.name}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">새 종목명</label>
              <input className={inputCls} placeholder="예: TQQQ, 동국제약"
                value={newStock} onChange={e => setNewStock(e.target.value)} />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
              <input type="checkbox" checked={newRealized} onChange={e => setNewRealized(e.target.checked)}
                className="w-4 h-4 rounded accent-blue-600" />
              실현 종목으로 표시
            </label>
            <button type="submit"
              className="w-full bg-slate-700 hover:bg-slate-800 text-white font-medium py-2.5 rounded-lg text-sm transition-colors">
              종목 추가
            </button>
            {addMsg && (
              <p className={`text-xs rounded-lg px-3 py-2 ${addMsg.type === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                {addMsg.text}
              </p>
            )}
          </form>

          {currentSection && currentSection.stocks.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">등록 종목</p>
              <div className="flex flex-wrap gap-1.5">
                {currentSection.stocks.map(s => (
                  <span key={s.name}
                    className="px-2.5 py-1 bg-slate-100 rounded-full text-xs text-slate-600 font-medium">
                    {s.name}{s.realized ? ' ✓' : ''}
                  </span>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
