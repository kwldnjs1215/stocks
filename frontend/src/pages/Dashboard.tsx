import { useEffect, useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { Card, KpiCard, SectionHeader, Divider } from '../components/Card'
import { fmtKrw, fmtAmount, fmtRate, colorClass, MONTHS } from '../lib/utils'
import { apiJson } from '../lib/api'

interface MonthlyStat { month: string; profit: number; cumulative: number }
interface StockMonthly { month: string; [stock: string]: number | string }
interface Section {
  name: string; currency: string; total: number; total_krw: number
  total_by_year: Record<string, number>
  stocks: { name: string; realized: boolean }[]
  monthly: MonthlyStat[]
  monthly_by_year: Record<string, MonthlyStat[]>
  stocks_monthly: StockMonthly[]
  stocks_monthly_by_year: Record<string, StockMonthly[]>
}
interface YearlySummary {
  year: number; realized_profit_krw: number; manual_profit_krw?: number
  sells: number; wins: number; win_rate: number; avg_hold_days: number
  year_principal: number; year_delta: number; return_rate: number
}
interface DashboardData {
  current_principal: number; total_profit_krw: number
  settings: { usd_to_krw_rate: number }
  sections: Section[]; yearly_summary: YearlySummary[]
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4']

interface Props { refreshKey?: number }

export default function Dashboard({ refreshKey = 0 }: Props) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    apiJson<DashboardData>('/api/dashboard')
      .then(d => {
        setData(d)
        if (d.yearly_summary?.length) {
          setSelectedYear(d.yearly_summary[d.yearly_summary.length - 1].year)
        }
      })
      .catch(e => setError(e instanceof Error ? e.message : '대시보드 데이터를 불러오지 못했습니다.'))
  }, [refreshKey])

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-red-500 text-sm font-medium">대시보드 데이터를 불러오지 못했습니다.</p>
        <p className="text-slate-400 text-xs">{error}</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const { current_principal, sections, yearly_summary, settings } = data
  const displayYear = selectedYear ?? yearly_summary[yearly_summary.length - 1]?.year ?? new Date().getFullYear()
  const displayYearKey = displayYear.toString()
  const getSectionTotal = (section: Section) =>
    section.total_by_year[displayYearKey] != null ? section.total_by_year[displayYearKey] : section.total
  const selectedYearTotalKrw = sections.reduce((sum, section) => {
    const total = getSectionTotal(section)
    return sum + (section.currency === 'USD' ? Math.round(total * settings.usd_to_krw_rate) : total)
  }, 0)
  const returnRate = current_principal > 0 ? (selectedYearTotalKrw / current_principal) * 100 : 0

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800">대시보드</h1>
        <p className="text-sm text-slate-400 mt-1">실현손익 기준 수익 현황</p>
      </div>

      {/* KPI 카드 */}
      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label={`${displayYear}년 총 수익`}
          value={fmtKrw(selectedYearTotalKrw)}
          valueClass={colorClass(selectedYearTotalKrw)}
          sub={`현재 원금 ${fmtKrw(current_principal)}`}
        />
        <KpiCard
          label="누적 수익률"
          value={fmtRate(returnRate)}
          valueClass={colorClass(returnRate)}
        />
        {sections.map(s => (
          <KpiCard
            key={s.name}
            label={`${s.name} 수익`}
            value={fmtAmount(getSectionTotal(s), s.currency)}
            valueClass={colorClass(getSectionTotal(s))}
          />
        ))}
      </div>

      {/* 연도별 성과 */}
      {yearly_summary.length > 0 && (
        <>
          <Divider />
          <SectionHeader title="연도별 원금 대비 수익률" />
          <div className="flex gap-2 flex-wrap mb-4">
            {yearly_summary.map(y => (
              <button
                key={y.year}
                onClick={() => setSelectedYear(y.year)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
                  selectedYear === y.year
                    ? 'bg-blue-600 text-white'
                    : 'bg-white border border-slate-200 text-slate-600 hover:border-blue-300'
                }`}
              >
                {y.year}년
              </button>
            ))}
          </div>

          {selectedYear && (() => {
            const y = yearly_summary.find(r => r.year === selectedYear)!
            return (
              <div className="grid grid-cols-4 gap-4">
                <KpiCard label="실현손익 (합계)" value={fmtKrw(y.realized_profit_krw)} valueClass={colorClass(y.realized_profit_krw)}
                  sub={y.manual_profit_krw ? `수동입력 ${fmtKrw(y.manual_profit_krw)} 포함` : undefined} />
                <KpiCard label="연도 반영 원금" value={fmtKrw(y.year_principal)} />
                <KpiCard label="원금 변동" value={fmtKrw(y.year_delta)} valueClass={colorClass(y.year_delta)} />
                <KpiCard label="수익률" value={fmtRate(y.return_rate)} valueClass={colorClass(y.return_rate)}
                  sub={y.sells > 0 ? `매도 ${y.sells}회  승률 ${y.win_rate}%  평균 ${y.avg_hold_days}일` : '수동입력 기준'} />
              </div>
            )
          })()}
        </>
      )}

      {/* 섹션별 월별 차트 */}
      {sections.map(section => {
        // 연도 선택 시 해당 연도 데이터, 없으면 전체
        const yearKey = selectedYear?.toString() ?? ''
        const monthly = (yearKey && section.monthly_by_year[yearKey]) ? section.monthly_by_year[yearKey] : section.monthly
        const stocksMonthly = (yearKey && section.stocks_monthly_by_year?.[yearKey])
          ? section.stocks_monthly_by_year[yearKey]
          : section.stocks_monthly
        const sectionTotal = (yearKey && section.total_by_year[yearKey] != null)
          ? section.total_by_year[yearKey]
          : section.total
        const yearLabel = selectedYear ? `${selectedYear}년` : '전체'

        return (
          <div key={section.name}>
            <Divider />
            <SectionHeader
              title={section.name}
              sub={`${yearLabel} ${fmtAmount(sectionTotal, section.currency)}`}
            />
            <div className="grid grid-cols-2 gap-4">
              {/* 월별 수익 막대 */}
              <Card className="p-5">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                  월별 수익 ({yearLabel})
                </p>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={monthly} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false}
                      tickFormatter={v => section.currency === 'USD' ? `$${(v/1000).toFixed(1)}K` : `${(v/10000).toFixed(0)}만`} />
                    <Tooltip formatter={(v) => [fmtAmount(Number(v), section.currency), '수익']} />
                    <Bar dataKey="profit" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>

              {/* 종목별 누적 수익 */}
              <Card className="p-5">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                  종목별 누적 수익 ({yearLabel})
                </p>
                {section.stocks.length === 0 ? (
                  <div className="h-[200px] flex items-center justify-center text-slate-400 text-sm">
                    등록된 종목 없음
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={stocksMonthly} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false}
                        tickFormatter={v => section.currency === 'USD' ? `$${(v/1000).toFixed(1)}K` : `${(v/10000).toFixed(0)}만`} />
                      <Tooltip formatter={(v, name) => [fmtAmount(Number(v), section.currency), String(name)]} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      {section.stocks.map((s, i) => (
                        <Area
                          key={s.name}
                          type="monotone"
                          dataKey={s.name}
                          stroke={COLORS[i % COLORS.length]}
                          fill={COLORS[i % COLORS.length] + '20'}
                          strokeWidth={2}
                        />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </Card>
            </div>

            {/* 월별 상세 테이블 */}
            <details className="mt-3">
              <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-600 select-none">
                월별 상세 내역 보기 ({yearLabel})
              </summary>
              <Card className="mt-2 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400">월</th>
                      {section.stocks.map(s => (
                        <th key={s.name} className="text-right px-4 py-3 text-xs font-semibold text-slate-400">
                          {s.name}{s.realized ? '+' : ''}
                        </th>
                      ))}
                      <th className="text-right px-4 py-3 text-xs font-semibold text-slate-400">합계</th>
                    </tr>
                  </thead>
                  <tbody>
                    {MONTHS.map((mon, idx) => {
                      const row = monthly[idx]
                      if (!row) return null
                      // 해당 월의 종목별 값: monthly에는 profit만 있으므로 rows_by_year에서 직접 읽음
                      return (
                        <tr key={mon} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                          <td className="px-4 py-2.5 text-slate-600 font-medium">{mon}</td>
                          {section.stocks.map(s => {
                            const stockRow = (stocksMonthly.find(r => r.month === mon) || {}) as Record<string, number | string>
                            const prevRow = (idx > 0 ? stocksMonthly.find(r => r.month === MONTHS[idx - 1]) : null) as Record<string, number | string> | null
                            const prev = prevRow ? (prevRow[s.name] as number || 0) : 0
                            const val = (stockRow[s.name] as number || 0) - prev
                            return (
                              <td key={s.name} className={`px-4 py-2.5 text-right ${colorClass(val)}`}>
                                {val !== 0 ? fmtAmount(val, section.currency) : '—'}
                              </td>
                            )
                          })}
                          <td className={`px-4 py-2.5 text-right font-semibold ${colorClass(row.profit)}`}>
                            {row.profit !== 0 ? fmtAmount(row.profit, section.currency) : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </Card>
            </details>
          </div>
        )
      })}
    </div>
  )
}
