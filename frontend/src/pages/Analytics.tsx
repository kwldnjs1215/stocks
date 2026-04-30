import { useEffect, useState } from 'react'
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { Card, KpiCard, SectionHeader, Divider } from '../components/Card'
import { fmtKrw, fmtAmount, colorClass, MONTHS } from '../lib/utils'
import { apiJson } from '../lib/api'
import { TrendingUp, TrendingDown, Clock, Target, Zap, AlertCircle, Lightbulb, Shield, BarChart3, Scale } from 'lucide-react'

interface AnnualRow {
  year: number; realized_profit_krw: number; sells: number
  wins: number; losses: number; win_rate: number; avg_hold_days: number
}
interface SymbolRow { 종목명: string; 실현손익: number }
interface SymbolCount { 종목명: string; 매도횟수: number }
interface SymbolTrade { 종목명: string; 거래횟수: number }
interface Style { label: string; avg_hold_days: number; traits: string[] }
interface ManualStockTotal { name: string; total: number; realized: boolean }
interface ManualSection {
  name: string; currency: string; total: number; total_krw: number
  monthly: { month: string; profit: number; cumulative: number }[]
  stock_totals: ManualStockTotal[]
}
interface AnalyticsData {
  annual: AnnualRow[]
  symbol_profit: SymbolRow[]
  symbol_count: SymbolCount[]
  symbol_trade: SymbolTrade[]
  monthly_profit: Record<string, Record<string, number>>
  buy_count: number; sell_count: number
  usd_trade_count: number; krw_trade_count: number
  style: Style; tips: string[]
  manual_sections: ManualSection[]
}

interface NarrativeBlock { heading: string; body: string }

function buildNarrativeBlocks(d: AnalyticsData): NarrativeBlock[] {
  const { annual, buy_count, sell_count, usd_trade_count } = d
  if (!annual.length) return []

  const totalSells = annual.reduce((s, r) => s + r.sells, 0)
  const totalWins = annual.reduce((s, r) => s + r.wins, 0)
  const winRate = totalSells > 0 ? (totalWins / totalSells * 100) : 0
  const years = annual.map(r => r.year)
  const first = annual[0], last = annual[annual.length - 1]
  const totalTrades = buy_count + sell_count
  const usdRatio = totalTrades > 0 ? Math.round(usd_trade_count / totalTrades * 100) : 0

  // 연도별 효율 (건당 수익)
  const efficiency = annual.map(r => ({
    year: r.year, perTrade: r.sells > 0 ? r.realized_profit_krw / r.sells : 0,
    sells: r.sells, avgHold: r.avg_hold_days, profit: r.realized_profit_krw,
  }))
  const bestEff = efficiency.reduce((a, b) => a.perTrade > b.perTrade ? a : b)

  // 스타일 변화 감지
  const holdTrend = last.avg_hold_days < first.avg_hold_days ? '단기화' : '장기화'
  const activityTrend = last.sells > (totalSells / annual.length) * 1.5 ? 'high' : 'normal'

  const blocks: NarrativeBlock[] = []

  // 블록 1: 스타일 변화 흐름
  if (years.length > 2) {
    const midYears = annual.slice(1, -1)
    const midAvgHold = midYears.reduce((s, r) => s + r.avg_hold_days, 0) / midYears.length
    const styleShift = midAvgHold > 200
      ? `중반부(${midYears[0].year}~${midYears[midYears.length - 1].year}년)에는 평균 ${Math.round(midAvgHold)}일씩 들고 가는 장기 보유 전략을 택했고`
      : `중반부에는 중단기 보유 위주로 운영했고`

    blocks.push({
      heading: '매매 스타일 변화',
      body: `${first.year}년 평균 ${first.avg_hold_days.toFixed(0)}일 보유로 시작해, ${styleShift}, ` +
        `최근 ${last.year}년에는 ${last.avg_hold_days.toFixed(0)}일로 ${holdTrend}됐습니다. ` +
        `이처럼 보유 기간이 크게 바뀐 건 단순한 변덕이 아니라, 시장 환경이나 집중도 변화에 맞게 스스로 전략을 조정해온 흔적으로 볼 수 있습니다.`,
    })
  }

  // 블록 2: 핵심 강점 — 승률
  blocks.push({
    heading: '핵심 강점: 일관된 승률',
    body: `${years[0]}년부터 ${years[years.length - 1]}년까지 전체 승률이 ${winRate.toFixed(0)}%입니다. ` +
      `단 한 해도 ${Math.min(...annual.map(r => r.win_rate)).toFixed(0)}% 아래로 떨어지지 않았다는 건, ` +
      `종목 선택 자체에 일관된 기준이 있다는 뜻입니다. ` +
      `이 수준의 승률을 가진 투자자의 수익을 결정하는 건 '얼마나 맞추느냐'가 아니라 '이겼을 때 얼마나 크게 이기느냐'입니다.`,
  })

  // 블록 3: 효율 분석
  if (bestEff.sells > 0) {
    blocks.push({
      heading: '효율의 정점',
      body: `${bestEff.year}년은 ${bestEff.sells}번의 매도로 건당 평균 ${Math.round(bestEff.perTrade).toLocaleString('ko-KR')}원을 벌었습니다 — ` +
        `전체 기간 중 가장 높은 건당 효율입니다. ` +
        (bestEff.avgHold > 100
          ? `당시 평균 ${bestEff.avgHold.toFixed(0)}일을 들고 있었는데, 이 장기 보유 패턴이 수익을 키운 핵심 요인이었습니다.`
          : `빠르게 들어갔다가 정확히 빠지는 타이밍이 맞아떨어진 해였습니다.`),
    })
  }

  // 블록 4: 최근 활동 변화 해석
  if (activityTrend === 'high' && annual.length > 1) {
    const prevAvgSells = (totalSells - last.sells) / (annual.length - 1)
    blocks.push({
      heading: `${last.year}년 매매 급증의 의미`,
      body: `${last.year}년 매도 횟수(${last.sells}회)는 이전 연평균(${prevAvgSells.toFixed(0)}회)의 약 ${(last.sells / Math.max(prevAvgSells, 1)).toFixed(1)}배입니다. ` +
        `활동량 증가 자체는 시장을 더 적극적으로 보고 있다는 긍정적 신호입니다. ` +
        `다만 이 시기에 건당 수익 규모가 유지되고 있는지 점검하는 것이 중요합니다 — ` +
        `자주 치고 빠지더라도 한 번 벌 때 제대로 버는 구조가 유지돼야 복리 효과가 쌓입니다.`,
    })
  }

  // 블록 5: 포트폴리오 구성
  blocks.push({
    heading: '포트폴리오 성격',
    body: usdRatio >= 50
      ? `전체 거래의 ${usdRatio}%가 미국 주식으로, 글로벌 시장 중심의 포트폴리오입니다. ` +
        `환율 영향을 받는 구조이므로, 달러 강세 시기와 약세 시기에 따라 실제 원화 수익이 달라질 수 있습니다.`
      : `국내 주식 비중이 ${100 - usdRatio}%로 높습니다. ` +
        `국내 시장 중심으로 운영하면서도 미국 ETF나 레버리지 상품을 병행하는 혼합형 전략을 택하고 있습니다.`,
  })

  return blocks
}

const TIP_ICONS = [Zap, Target, TrendingUp, AlertCircle, Lightbulb, Shield, BarChart3, Scale]

interface Props { refreshKey?: number }

export default function Analytics({ refreshKey = 0 }: Props) {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | null>(null)
  const [justUpdated, setJustUpdated] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    setError(null)
    apiJson<AnalyticsData>('/api/analytics', 15000)
      .then(d => {
        setData(d)
        if (d.annual?.length) setSelectedYear(d.annual[d.annual.length - 1].year)
        if (refreshKey > 0) {
          setJustUpdated(true)
          setTimeout(() => setJustUpdated(false), 2500)
        }
      })
      .catch(e => setError(e.message ?? '알 수 없는 오류'))
  }, [refreshKey, retryCount])

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-red-500 text-sm font-medium">분석 데이터를 불러오지 못했습니다.</p>
        <p className="text-slate-400 text-xs">{error}</p>
        <button
          onClick={() => { setError(null); setData(null); setRetryCount(c => c + 1) }}
          className="text-xs text-blue-500 underline"
        >다시 시도</button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-slate-400 text-xs">XLS 파일 분석 중…</p>
      </div>
    )
  }

  if (!data.annual.length) {
    return <div className="text-slate-500 text-sm">분석할 매도 내역이 없습니다.</div>
  }

  const totalSells = data.annual.reduce((s, r) => s + r.sells, 0)
  const totalWins = data.annual.reduce((s, r) => s + r.wins, 0)
  const totalProfit = data.annual.reduce((s, r) => s + r.realized_profit_krw, 0)
  const avgHold = data.annual.reduce((s, r) => s + r.avg_hold_days, 0) / data.annual.length
  const overallWinRate = totalSells > 0 ? (totalWins / totalSells * 100) : 0
  const narrativeBlocks = buildNarrativeBlocks(data)

  const monthlyData = MONTHS.map(m => ({
    month: m,
    profit: data.monthly_profit[String(selectedYear)]?.[m] ?? 0,
  }))

  const top10Profit = data.symbol_profit.slice(0, 10)
  const top10Count = data.symbol_count.slice(0, 10)

  return (
    <div className="space-y-6">
      {/* 업데이트 토스트 */}
      <div className={`fixed top-5 right-6 z-50 transition-all duration-500 ${justUpdated ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2 pointer-events-none'}`}>
        <div className="bg-slate-800 text-white text-sm px-4 py-2.5 rounded-xl shadow-lg flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          매매 입력 반영 완료
        </div>
      </div>

      <div>
        <h1 className="text-2xl font-bold text-slate-800">분석</h1>
        <p className="text-sm text-slate-400 mt-1">종합거래내역 기반 매매 패턴 분석</p>
      </div>

      {/* 내러티브 요약 — 블록형 */}
      <div className="grid grid-cols-2 gap-3">
        {narrativeBlocks.map((block, i) => (
          <Card key={i} className={`p-5 ${i === 0 ? 'col-span-2' : ''}`}>
            <p className="text-xs font-bold text-blue-500 uppercase tracking-wider mb-2">{block.heading}</p>
            <p className="text-sm text-slate-600 leading-relaxed">{block.body}</p>
          </Card>
        ))}
      </div>

      {/* KPI */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard label="총 매도 횟수" value={`${totalSells}회`} sub={`매수 ${data.buy_count} / 매도 ${data.sell_count}`} />
        <KpiCard label="전체 승률" value={`${overallWinRate.toFixed(1)}%`} valueClass={overallWinRate >= 50 ? 'text-red-500' : 'text-blue-500'}
          sub={`승 ${totalWins} / 패 ${totalSells - totalWins}`} />
        <KpiCard label="총 실현손익" value={fmtKrw(totalProfit)} valueClass={colorClass(totalProfit)} />
        <KpiCard label="평균 보유일" value={`${avgHold.toFixed(1)}일`} sub={`미국 ${data.usd_trade_count} / 국내 ${data.krw_trade_count}회`} />
      </div>

      {/* 매매 스타일 */}
      <Divider />
      <div className="grid grid-cols-2 gap-4">
        <Card className="p-5">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">매매 스타일</p>
          <div className="flex items-center gap-3 mb-3">
            <span className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-sm font-bold">
              {data.style.label}
            </span>
            <span className="text-slate-400 text-sm">평균 보유 {data.style.avg_hold_days}일</span>
          </div>
          <ul className="space-y-2">
            {data.style.traits.map((t, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-600">
                <span className="text-blue-400 mt-0.5">•</span>
                {t}
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-5">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">패턴 요약</p>
          <ul className="space-y-2">
            {data.symbol_profit.length > 0 && (() => {
              const best = data.symbol_profit[0]
              const worst = data.symbol_profit[data.symbol_profit.length - 1]
              const topTrade = data.symbol_trade[0]
              return (
                <>
                  <li className="flex items-center gap-2 text-sm text-slate-600">
                    <TrendingUp size={14} className="text-emerald-500 shrink-0" />
                    최고 종목: <span className="font-semibold text-slate-800">{best.종목명}</span>
                    <span className="text-emerald-600 ml-auto">{fmtKrw(best.실현손익)}</span>
                  </li>
                  <li className="flex items-center gap-2 text-sm text-slate-600">
                    <TrendingDown size={14} className="text-red-400 shrink-0" />
                    최대 손실: <span className="font-semibold text-slate-800">{worst.종목명}</span>
                    <span className={`ml-auto ${colorClass(worst.실현손익)}`}>{fmtKrw(worst.실현손익)}</span>
                  </li>
                  {data.symbol_count[0] && (
                    <li className="flex items-center gap-2 text-sm text-slate-600">
                      <Target size={14} className="text-blue-400 shrink-0" />
                      가장 많이 매도: <span className="font-semibold text-slate-800">{data.symbol_count[0].종목명}</span>
                      <span className="text-slate-500 ml-auto">{data.symbol_count[0].매도횟수}회</span>
                    </li>
                  )}
                  {topTrade && (
                    <li className="flex items-center gap-2 text-sm text-slate-600">
                      <Clock size={14} className="text-amber-400 shrink-0" />
                      가장 많이 거래: <span className="font-semibold text-slate-800">{topTrade.종목명}</span>
                      <span className="text-slate-500 ml-auto">총 {topTrade.거래횟수}회</span>
                    </li>
                  )}
                </>
              )
            })()}
          </ul>
        </Card>
      </div>

      {/* 연도별 실현손익 */}
      <Divider />
      <SectionHeader title="연도별 실현손익" />
      <Card className="p-5">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.annual} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="year" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false}
              tickFormatter={v => `${(v / 10000).toFixed(0)}만`} />
            <Tooltip
              formatter={(v) => [fmtKrw(Number(v)), '실현손익']}
              labelFormatter={l => `${l}년`}
            />
            <Bar dataKey="realized_profit_krw" radius={[6, 6, 0, 0]}>
              {data.annual.map(r => (
                <Cell key={r.year} fill={r.realized_profit_krw >= 0 ? '#ef4444' : '#3b82f6'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>

      {/* 연도별 상세 테이블 */}
      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              {['연도', '실현손익', '매도', '승률', '평균 보유일'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-400">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.annual.map(r => (
              <tr key={r.year} className="border-b border-slate-50 hover:bg-slate-50">
                <td className="px-4 py-3 font-semibold text-slate-700">{r.year}년</td>
                <td className={`px-4 py-3 font-semibold ${colorClass(r.realized_profit_krw)}`}>{fmtKrw(r.realized_profit_krw)}</td>
                <td className="px-4 py-3 text-slate-600">{r.sells}회</td>
                <td className={`px-4 py-3 font-medium ${r.win_rate >= 50 ? 'text-red-500' : 'text-blue-500'}`}>{r.win_rate.toFixed(1)}%</td>
                <td className="px-4 py-3 text-slate-600">{r.avg_hold_days.toFixed(1)}일</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* 월별 실현손익 */}
      <Divider />
      <div className="flex items-center justify-between mb-4">
        <SectionHeader title="월별 실현손익" />
        <div className="flex gap-2">
          {data.annual.map(r => (
            <button key={r.year}
              onClick={() => setSelectedYear(r.year)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${
                selectedYear === r.year ? 'bg-blue-600 text-white' : 'bg-white border border-slate-200 text-slate-500 hover:border-blue-300'
              }`}
            >
              {r.year}
            </button>
          ))}
        </div>
      </div>
      <Card className="p-5">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={monthlyData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="month" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false}
              tickFormatter={v => `${(v / 10000).toFixed(0)}만`} />
            <Tooltip formatter={(v) => [fmtKrw(Number(v)), '실현손익']} />
            <Line type="monotone" dataKey="profit" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }}
              activeDot={{ r: 6 }} />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      {/* 종목별 랭킹 */}
      <Divider />
      <div className="grid grid-cols-2 gap-4">
        {/* 실현손익 랭킹 */}
        <div>
          <SectionHeader title="종목별 실현손익 TOP 10" />
          <Card className="overflow-hidden">
            {(() => {
              const maxAbs = Math.max(...top10Profit.map(r => Math.abs(r.실현손익)), 1)
              return top10Profit.map((r, i) => (
                <div key={r.종목명}
                  className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-50 last:border-0 hover:bg-slate-50">
                  <span className="text-xs font-bold text-slate-300 w-4 shrink-0">{i + 1}</span>
                  <span className="text-sm text-slate-700 flex-1 truncate min-w-0" title={r.종목명}>{r.종목명}</span>
                  <div className="w-20 bg-slate-100 rounded-full h-1.5 shrink-0">
                    <div className="h-1.5 rounded-full transition-all"
                      style={{ width: `${Math.abs(r.실현손익) / maxAbs * 100}%`, background: r.실현손익 >= 0 ? '#ef4444' : '#3b82f6' }} />
                  </div>
                  <span className={`text-xs font-semibold w-24 text-right shrink-0 ${r.실현손익 >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
                    {fmtKrw(r.실현손익)}
                  </span>
                </div>
              ))
            })()}
          </Card>
        </div>

        {/* 매도 횟수 랭킹 */}
        <div>
          <SectionHeader title="종목별 매도 횟수 TOP 10" />
          <Card className="overflow-hidden">
            {(() => {
              const maxCount = Math.max(...top10Count.map(r => r.매도횟수), 1)
              return top10Count.map((r, i) => (
                <div key={r.종목명}
                  className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-50 last:border-0 hover:bg-slate-50">
                  <span className="text-xs font-bold text-slate-300 w-4 shrink-0">{i + 1}</span>
                  <span className="text-sm text-slate-700 flex-1 truncate min-w-0" title={r.종목명}>{r.종목명}</span>
                  <div className="w-20 bg-slate-100 rounded-full h-1.5 shrink-0">
                    <div className="h-1.5 rounded-full bg-indigo-400 transition-all"
                      style={{ width: `${r.매도횟수 / maxCount * 100}%` }} />
                  </div>
                  <span className="text-xs font-semibold text-indigo-500 w-10 text-right shrink-0">
                    {r.매도횟수}회
                  </span>
                </div>
              ))
            })()}
          </Card>
        </div>
      </div>

      {/* 수동 입력 현황 — 매매 입력과 연동 */}
      {data.manual_sections.length > 0 && (
        <>
          <Divider />
          <SectionHeader
            title="수동 입력 현황"
            sub="매매 입력 페이지에서 직접 기록한 데이터 · 입력할 때마다 자동 업데이트"
          />
          <div className="grid grid-cols-2 gap-4">
            {data.manual_sections.map(section => {
              const hasData = section.stock_totals.length > 0
              const maxAbs = hasData ? Math.max(...section.stock_totals.map(s => Math.abs(s.total)), 1) : 1
              return (
                <Card key={section.name} className="overflow-hidden">
                  <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
                    <div>
                      <p className="text-sm font-bold text-slate-700">{section.name}</p>
                      <p className={`text-xs mt-0.5 font-semibold ${section.total >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
                        총 {fmtAmount(section.total, section.currency)}
                      </p>
                    </div>
                    <span className="text-xs bg-slate-100 text-slate-500 px-2 py-1 rounded-full">
                      {section.currency}
                    </span>
                  </div>
                  {hasData ? (
                    <div className="divide-y divide-slate-50">
                      {section.stock_totals.map(s => (
                        <div key={s.name} className="flex items-center gap-3 px-5 py-2.5 hover:bg-slate-50">
                          <span className="text-sm text-slate-700 flex-1 truncate min-w-0" title={s.name}>
                            {s.name}{s.realized ? <span className="text-blue-400 text-xs ml-1">실현</span> : ''}
                          </span>
                          <div className="w-16 bg-slate-100 rounded-full h-1.5 shrink-0">
                            <div className="h-1.5 rounded-full"
                              style={{ width: `${Math.abs(s.total) / maxAbs * 100}%`, background: s.total >= 0 ? '#ef4444' : '#3b82f6' }} />
                          </div>
                          <span className={`text-xs font-semibold w-24 text-right shrink-0 ${s.total >= 0 ? 'text-red-500' : 'text-blue-500'}`}>
                            {fmtAmount(s.total, section.currency)}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="px-5 py-6 text-sm text-slate-400 text-center">
                      아직 입력된 수익이 없습니다
                    </div>
                  )}
                  {/* 월별 미니 바 */}
                  <div className="px-5 py-3 border-t border-slate-50 flex items-end gap-1 h-14">
                    {section.monthly.map(m => {
                      const monthMax = Math.max(...section.monthly.map(x => Math.abs(x.profit)), 1)
                      const h = Math.round(Math.abs(m.profit) / monthMax * 32)
                      return (
                        <div key={m.month} className="flex-1 flex flex-col items-center justify-end" title={`${m.month}: ${fmtAmount(m.profit, section.currency)}`}>
                          {m.profit !== 0 && (
                            <div className="w-full rounded-sm" style={{ height: h, background: m.profit >= 0 ? '#fca5a5' : '#93c5fd' }} />
                          )}
                        </div>
                      )
                    })}
                  </div>
                </Card>
              )
            })}
          </div>
        </>
      )}

      {/* 개선 팁 */}
      <Divider />
      <SectionHeader title="수익률을 올리기 위해 해볼 것" sub="데이터 기반 맞춤 조언" />
      <div className="space-y-3">
        {data.tips.map((tip, i) => {
          const Icon = TIP_ICONS[i % TIP_ICONS.length]
          return (
            <Card key={i} className="p-4 flex items-start gap-4">
              <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center shrink-0 mt-0.5">
                <Icon size={15} className="text-amber-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-600 leading-relaxed">{tip}</p>
              </div>
              <span className="text-xs text-slate-300 font-bold shrink-0 mt-1">{i + 1}</span>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
