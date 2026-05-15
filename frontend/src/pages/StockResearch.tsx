import { useState } from 'react'
import { Search, RefreshCw, Send, TrendingUp, TrendingDown, Activity, MessageSquare } from 'lucide-react'
import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, SectionHeader } from '../components/Card'

interface Analysis {
  symbol: string
  market: string
  exchange: string
  updated_at: string
  data_source: string
  quote: { price: number; change_pct: number; volume: number }
  technical: {
    rsi14: number | null
    rsi_comment: string
    ma5: number | null
    ma20: number | null
    ma60: number | null
    trend: string
    recent_low: number
    recent_high: number
  }
  weekly_flow: Array<{ date: string; close: number; change_pct: number; volume: number }>
  levels: {
    support: { price: number; reason: string }
    resistance: { price: number; reason: string }
  }
  short_term_levels: {
    available: boolean
    source?: string
    timeframe?: string
    support?: { price: number; time: string; reason: string }
    resistance?: { price: number; time: string; reason: string }
    message?: string
    bars: Array<{ time: string; close: number; volume: number }>
  }
  pressure: { buy_pct: number; sell_pct: number; obv_bias: string; volume_ratio: number; comment: string }
  options: {
    available: boolean
    source?: string
    expiry?: string
    call_volume?: number
    put_volume?: number
    put_call_volume_ratio?: number | null
    max_pain?: number
    spot_vs_max_pain_pct?: number | null
    message?: string
  }
  peers: Array<{ symbol: string; price: number; change_5d: number }>
  company: { sector?: string; industry?: string; summary?: string; earnings_dates?: string[] }
  news: Array<{ title: string; url: string; date: string }>
  events: { past: string[]; future: string[] }
  llm_strategy: { available: boolean; source?: string; text?: string; message?: string }
  notes: string[]
}

interface ChatMsg {
  role: 'user' | 'assistant'
  text: string
}

function fmtPct(v?: number | null) {
  if (v === null || v === undefined) return '-'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function fmtNum(v?: number | null) {
  if (v === null || v === undefined) return '-'
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function MiniMetric({ label, value, sub, tone = 'slate' }: { label: string; value: string; sub?: string; tone?: 'red' | 'blue' | 'slate' | 'violet' }) {
  const toneClass = {
    red: 'text-red-500 bg-red-50',
    blue: 'text-blue-500 bg-blue-50',
    violet: 'text-violet-500 bg-violet-50',
    slate: 'text-slate-700 bg-slate-50',
  }[tone]
  return (
    <Card className="p-4">
      <p className="text-[11px] font-semibold text-slate-400">{label}</p>
      <p className={`inline-block mt-1 text-xl font-bold px-2 py-0.5 rounded ${toneClass}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-2 leading-relaxed">{sub}</p>}
    </Card>
  )
}

function PeerRow({ peer }: { peer: Analysis['peers'][number] }) {
  const up = peer.change_5d >= 0
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
      <span className="text-sm font-semibold text-slate-700">{peer.symbol}</span>
      <div className="text-right">
        <p className="text-xs text-slate-400">{fmtNum(peer.price)}</p>
        <p className={`text-xs font-bold ${up ? 'text-red-500' : 'text-blue-500'}`}>{fmtPct(peer.change_5d)}</p>
      </div>
    </div>
  )
}

export default function StockResearch() {
  const [symbol, setSymbol] = useState('샌디스크')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [chat, setChat] = useState<ChatMsg[]>([])

  const runAnalysis = async () => {
    if (!symbol.trim()) return
    setLoading(true)
    setError(null)
    setChat([])
    try {
      const resp = await fetch('/api/stock-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol }),
      })
      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || '분석 실패')
      }
      setAnalysis(await resp.json())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const ask = async () => {
    if (!analysis || !question.trim()) return
    const userText = question.trim()
    setQuestion('')
    setChat(prev => [...prev, { role: 'user', text: userText }])
    try {
      const resp = await fetch('/api/stock-analysis/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analysis, question: userText }),
      })
      const data = await resp.json()
      setChat(prev => [...prev, { role: 'assistant', text: data.answer || '답변을 만들지 못했습니다.' }])
    } catch {
      setChat(prev => [...prev, { role: 'assistant', text: '추가 분석 호출에 실패했습니다.' }])
    }
  }

  const up = (analysis?.quote.change_pct ?? 0) >= 0

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-800">종목 분석</h1>
          <p className="text-xs text-slate-400 mt-0.5">한국투자 API 우선, 보조 데이터로 기술지표와 옵션 체인 계산</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') runAnalysis() }}
              placeholder="샌디스크, SNDK, 삼성전자..."
              className="w-72 rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-400"
            />
          </div>
          <button
            onClick={runAnalysis}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            분석
          </button>
        </div>
      </div>

      {error && <Card className="p-5 text-sm text-red-500">{error}</Card>}

      {!analysis && !loading && !error && (
        <Card className="p-8 text-center">
          <Activity size={28} className="mx-auto text-blue-500 mb-3" />
          <p className="text-sm font-semibold text-slate-700">종목명을 넣고 분석을 눌러보세요.</p>
          <p className="text-xs text-slate-400 mt-1">예: 샌디스크, SNDK, 엔비디아, 삼성전자</p>
        </Card>
      )}

      {loading && (
        <div className="flex items-center justify-center h-64 text-sm text-slate-400">
          시세, 옵션, 관련주 데이터를 모으는 중...
        </div>
      )}

      {analysis && !loading && (
        <>
          <Card className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-slate-400">{analysis.market} · {analysis.exchange} · {analysis.data_source}</p>
                <h2 className="text-3xl font-bold text-slate-800 mt-1">{analysis.symbol}</h2>
                <p className="text-xs text-slate-400 mt-1">업데이트: {analysis.updated_at}</p>
              </div>
              <div className="text-right">
                <p className="text-3xl font-bold text-slate-800">{fmtNum(analysis.quote.price)}</p>
                <p className={`text-sm font-bold mt-1 ${up ? 'text-red-500' : 'text-blue-500'}`}>
                  {up ? <TrendingUp size={14} className="inline mr-1" /> : <TrendingDown size={14} className="inline mr-1" />}
                  {fmtPct(analysis.quote.change_pct)}
                </p>
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-4 gap-4">
            <MiniMetric label="RSI 14" value={analysis.technical.rsi14?.toFixed(2) ?? '-'} sub={analysis.technical.rsi_comment} tone={analysis.technical.rsi14 && analysis.technical.rsi14 > 70 ? 'red' : analysis.technical.rsi14 && analysis.technical.rsi14 < 30 ? 'blue' : 'slate'} />
            <MiniMetric label="이평선" value={analysis.technical.trend} sub={`5일 ${fmtNum(analysis.technical.ma5)} · 20일 ${fmtNum(analysis.technical.ma20)} · 60일 ${fmtNum(analysis.technical.ma60)}`} tone="violet" />
            <MiniMetric label="최근 저가/고가" value={`${fmtNum(analysis.technical.recent_low)} / ${fmtNum(analysis.technical.recent_high)}`} sub="최근 120거래일 기준" />
            <MiniMetric label="수급 압력" value={`${analysis.pressure.buy_pct}% / ${analysis.pressure.sell_pct}%`} sub={`${analysis.pressure.obv_bias} · 평균 대비 ${analysis.pressure.volume_ratio}배`} tone={analysis.pressure.buy_pct >= analysis.pressure.sell_pct ? 'red' : 'blue'} />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <Card className="p-5 col-span-2">
              <SectionHeader title="일주일 주가 흐름" sub="종가 기준" />
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={analysis.weekly_flow} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis domain={['auto', 'auto']} tick={{ fontSize: 11 }} width={50} />
                  <Tooltip formatter={(value) => fmtNum(Number(value))} />
                  <Line type="monotone" dataKey="close" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </Card>
            <Card className="p-5">
              <SectionHeader title="중기 지지/저항" />
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-slate-400">하방 지지선</p>
                  <p className="text-2xl font-bold text-blue-500">{fmtNum(analysis.levels.support.price)}</p>
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">{analysis.levels.support.reason}</p>
                </div>
                <div className="border-t border-slate-100 pt-4">
                  <p className="text-xs text-slate-400">상방 저항선</p>
                  <p className="text-2xl font-bold text-red-500">{fmtNum(analysis.levels.resistance.price)}</p>
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">{analysis.levels.resistance.reason}</p>
                </div>
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <Card className="p-5 col-span-2">
              <SectionHeader title="단기 지지/저항" sub={analysis.short_term_levels.available ? analysis.short_term_levels.timeframe : '5분봉 기준'} />
              {analysis.short_term_levels.available && analysis.short_term_levels.support && analysis.short_term_levels.resistance ? (
                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-lg bg-blue-50 p-4">
                    <p className="text-xs text-blue-400">단기 지지</p>
                    <p className="text-2xl font-bold text-blue-600 mt-1">{fmtNum(analysis.short_term_levels.support.price)}</p>
                    <p className="text-xs text-blue-500 mt-2 leading-relaxed">{analysis.short_term_levels.support.reason}</p>
                  </div>
                  <div className="rounded-lg bg-red-50 p-4">
                    <p className="text-xs text-red-400">단기 저항</p>
                    <p className="text-2xl font-bold text-red-600 mt-1">{fmtNum(analysis.short_term_levels.resistance.price)}</p>
                    <p className="text-xs text-red-500 mt-2 leading-relaxed">{analysis.short_term_levels.resistance.reason}</p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-400">{analysis.short_term_levels.message}</p>
              )}
            </Card>
            <Card className="p-5">
              <SectionHeader title="5분봉 흐름" sub={analysis.short_term_levels.source} />
              {analysis.short_term_levels.available ? (
                <ResponsiveContainer width="100%" height={170}>
                  <LineChart data={analysis.short_term_levels.bars} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                    <XAxis dataKey="time" hide />
                    <YAxis domain={['auto', 'auto']} hide />
                    <Tooltip formatter={(value) => fmtNum(Number(value))} />
                    <Line type="monotone" dataKey="close" stroke="#0f172a" strokeWidth={1.8} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-slate-400">차트 없음</p>
              )}
            </Card>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <Card className="p-5">
              <SectionHeader title="옵션 분석" sub={analysis.options.available ? `${analysis.options.expiry} 만기` : undefined} />
              {analysis.options.available ? (
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between"><span className="text-slate-400">콜 거래량</span><b>{fmtNum(analysis.options.call_volume)}</b></div>
                  <div className="flex justify-between"><span className="text-slate-400">풋 거래량</span><b>{fmtNum(analysis.options.put_volume)}</b></div>
                  <div className="flex justify-between"><span className="text-slate-400">P/C Ratio</span><b>{fmtNum(analysis.options.put_call_volume_ratio)}</b></div>
                  <div className="flex justify-between"><span className="text-slate-400">맥스페인</span><b>{fmtNum(analysis.options.max_pain)}</b></div>
                </div>
              ) : <p className="text-sm text-slate-400">{analysis.options.message}</p>}
            </Card>
            <Card className="p-5">
              <SectionHeader title="관련 기업" sub="5거래일 흐름" />
              {analysis.peers.length ? analysis.peers.map(peer => <PeerRow key={peer.symbol} peer={peer} />) : <p className="text-sm text-slate-400">관련주 데이터 없음</p>}
            </Card>
            <Card className="p-5">
              <SectionHeader title="이벤트" sub={analysis.company.industry || analysis.company.sector} />
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-semibold text-slate-400 mb-1">과거</p>
                  {analysis.events.past.map(x => <p key={x} className="text-xs text-slate-600 leading-relaxed">· {x}</p>)}
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-400 mb-1">미래</p>
                  {analysis.events.future.map(x => <p key={x} className="text-xs text-slate-600 leading-relaxed">· {x}</p>)}
                </div>
              </div>
            </Card>
          </div>

          <Card className="p-5">
            <SectionHeader title="관련 뉴스/호재·악재 단서" sub="최근 헤드라인 기반" />
            {analysis.news.length ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                {analysis.news.map(n => (
                  <a key={n.url || n.title} href={n.url} target="_blank" rel="noreferrer" className="text-sm text-slate-600 hover:text-blue-600 border-b border-slate-50 pb-2">
                    {n.title}
                  </a>
                ))}
              </div>
            ) : <p className="text-sm text-slate-400">뉴스 데이터를 가져오지 못했습니다.</p>}
          </Card>

          <Card className="p-5">
            <SectionHeader title="Claude 전략 메모" sub={analysis.llm_strategy.available ? analysis.llm_strategy.source : 'API 키 필요'} />
            {analysis.llm_strategy.available ? (
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-600">{analysis.llm_strategy.text}</div>
            ) : (
              <p className="text-sm text-slate-400">{analysis.llm_strategy.message}</p>
            )}
          </Card>

          <Card className="p-5">
            <SectionHeader title="추가 질문" sub="현재 분석 결과를 바탕으로 답합니다" />
            <div className="space-y-3 max-h-72 overflow-y-auto mb-4">
              {chat.length === 0 && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <MessageSquare size={15} />
                  지지선이 깨지면 어디까지 볼지, 옵션이 무슨 뜻인지 물어보세요.
                </div>
              )}
              {chat.map((m, i) => (
                <div key={`${m.role}-${i}`} className={`text-sm rounded-lg px-3 py-2 ${m.role === 'user' ? 'ml-auto bg-blue-600 text-white w-fit max-w-[80%]' : 'bg-slate-50 text-slate-600 max-w-[88%]'}`}>
                  {m.text}
                </div>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={question}
                onChange={e => setQuestion(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') ask() }}
                placeholder="예: 맥스페인 기준으로 지금 과열이야?"
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-400"
              />
              <button onClick={ask} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white">
                <Send size={14} />
                질문
              </button>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
