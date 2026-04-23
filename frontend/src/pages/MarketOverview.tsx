import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Minus, Activity } from 'lucide-react'
import { Card, KpiCard, SectionHeader } from '../components/Card'

interface Sector {
  name: string
  change: number
}

interface IndexData {
  name: string
  price: number
  change: number
  change_val: number
}

interface MarketData {
  sectors: Sector[]
  rising: Sector[]
  falling: Sector[]
  flat: Sector[]
  indices: IndexData[]
  summary: {
    rising_count: number
    falling_count: number
    flat_count: number
    trend: string
  }
  updated_at: string
}

function changeColor(v: number) {
  if (v > 0) return 'text-red-500'
  if (v < 0) return 'text-blue-500'
  return 'text-slate-400'
}

function changeBg(v: number) {
  if (v >= 2) return 'bg-red-500'
  if (v >= 1) return 'bg-red-400'
  if (v >= 0.5) return 'bg-red-300'
  if (v <= -2) return 'bg-blue-500'
  if (v <= -1) return 'bg-blue-400'
  if (v <= -0.5) return 'bg-blue-300'
  return 'bg-slate-300'
}

function fmtChange(v: number) {
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function IndexCard({ idx }: { idx: IndexData }) {
  const up = idx.change >= 0
  return (
    <Card className="p-5 flex-1">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{idx.name}</p>
      <p className="text-2xl font-bold mt-1.5 text-slate-800">
        {idx.price.toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </p>
      <p className={`text-sm font-semibold mt-1 ${up ? 'text-red-500' : 'text-blue-500'}`}>
        {up ? '▲' : '▼'} {Math.abs(idx.change_val).toFixed(2)} ({fmtChange(idx.change)})
      </p>
    </Card>
  )
}

function SectorBar({ sector, maxAbs }: { sector: Sector; maxAbs: number }) {
  const pct = maxAbs > 0 ? Math.abs(sector.change) / maxAbs : 0
  const barWidth = `${Math.max(pct * 100, 2)}%`
  const isUp = sector.change >= 0

  return (
    <div className="flex items-center gap-3 py-1">
      <span className="text-xs text-slate-600 w-32 shrink-0 truncate">{sector.name}</span>
      <div className="flex-1 flex items-center gap-2">
        <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
          <div
            className={`h-2 rounded-full ${changeBg(sector.change)}`}
            style={{ width: barWidth }}
          />
        </div>
        <span className={`text-xs font-semibold w-14 text-right ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
          {fmtChange(sector.change)}
        </span>
      </div>
    </div>
  )
}

function RotationSummary({ data }: { data: MarketData }) {
  const top3up = data.rising.slice(0, 3).map(s => s.name).join(', ')
  const top3dn = data.falling.slice(data.falling.length - 3).reverse().map(s => s.name).join(', ')
  const { trend, rising_count, falling_count } = data.summary

  let rotationMsg = ''
  if (trend === '강세') {
    rotationMsg = `시장 전반이 올라가는 날입니다. ${top3up} 섹터가 주도하고 있으며, ${top3dn ? top3dn + ' 섹터는 아직 소외' : '낙오 섹터는 없음'}되어 있습니다.`
  } else if (trend === '약세') {
    rotationMsg = `전반적으로 하락세입니다. ${top3dn ? top3dn + ' 섹터가 하락을 주도' : ''}, ${top3up ? top3up + ' 섹터는 방어 중' : '방어 섹터 없음'}입니다.`
  } else {
    rotationMsg = `순환매 장세입니다. ${top3up ? top3up + ' 섹터로 자금이 유입' : ''}되고 있으며, ${top3dn ? top3dn + ' 섹터에서 차익 실현이 나오는' : ''} 흐름입니다.`
  }

  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <Activity size={18} className="text-violet-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-bold text-slate-700 mb-1">순환매 분석</p>
          <p className="text-sm text-slate-500 leading-relaxed">{rotationMsg}</p>
          <div className="mt-3 flex gap-4 text-xs text-slate-400">
            <span className="text-red-500 font-semibold">↑ {rising_count}개 상승</span>
            <span className="text-blue-500 font-semibold">↓ {falling_count}개 하락</span>
            <span className="text-slate-400 font-semibold">— {data.summary.flat_count}개 보합</span>
          </div>
        </div>
      </div>
    </Card>
  )
}

export default function MarketOverview() {
  const [data, setData] = useState<MarketData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async (forceRefresh = false) => {
    try {
      if (forceRefresh) setRefreshing(true)
      else setLoading(true)
      setError(null)

      const url = forceRefresh ? '/api/market/refresh' : '/api/market'
      const method = forceRefresh ? 'POST' : 'GET'
      const resp = await fetch(url, { method })
      if (!resp.ok) {
        const err = await resp.json()
        throw new Error(err.detail || '데이터 로드 실패')
      }
      setData(await resp.json())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
        네이버 금융에서 시황 데이터를 불러오는 중...
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-16">
        <p className="text-red-400 text-sm mb-4">{error}</p>
        <button onClick={() => load(true)} className="text-xs text-slate-500 underline">다시 시도</button>
      </div>
    )
  }

  if (!data) return null

  const maxAbs = Math.max(...data.sectors.map(s => Math.abs(s.change)), 0.01)
  const trendColor = data.summary.trend === '강세'
    ? 'text-red-500 bg-red-50'
    : data.summary.trend === '약세'
    ? 'text-blue-500 bg-blue-50'
    : 'text-violet-500 bg-violet-50'

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">시황</h1>
          <p className="text-xs text-slate-400 mt-0.5">업데이트: {data.updated_at} · 30분 캐시</p>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition disabled:opacity-40"
        >
          <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      {/* 지수 카드 */}
      <div className="flex gap-4">
        {data.indices.map(idx => <IndexCard key={idx.name} idx={idx} />)}
        <Card className="p-5 flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">시장 분위기</p>
            <span className={`text-2xl font-bold px-3 py-1 rounded-lg ${trendColor}`}>
              {data.summary.trend}
            </span>
          </div>
        </Card>
      </div>

      {/* 순환매 분석 */}
      <RotationSummary data={data} />

      {/* 상승 / 하락 섹터 */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionHeader
            title="상승 섹터"
            sub={`${data.rising.length}개 업종`}
          />
          {data.rising.length === 0
            ? <p className="text-xs text-slate-400">없음</p>
            : data.rising.map(s => (
              <div key={s.name} className="flex items-center justify-between py-1.5 border-b border-slate-50 last:border-0">
                <div className="flex items-center gap-2">
                  <TrendingUp size={13} className="text-red-400 shrink-0" />
                  <span className="text-sm text-slate-700">{s.name}</span>
                </div>
                <span className="text-sm font-bold text-red-500">{fmtChange(s.change)}</span>
              </div>
            ))
          }
        </Card>

        <Card className="p-5">
          <SectionHeader
            title="하락 섹터"
            sub={`${data.falling.length}개 업종`}
          />
          {data.falling.length === 0
            ? <p className="text-xs text-slate-400">없음</p>
            : [...data.falling].reverse().map(s => (
              <div key={s.name} className="flex items-center justify-between py-1.5 border-b border-slate-50 last:border-0">
                <div className="flex items-center gap-2">
                  <TrendingDown size={13} className="text-blue-400 shrink-0" />
                  <span className="text-sm text-slate-700">{s.name}</span>
                </div>
                <span className="text-sm font-bold text-blue-500">{fmtChange(s.change)}</span>
              </div>
            ))
          }
        </Card>
      </div>

      {/* 전체 섹터 바 차트 */}
      <Card className="p-5">
        <SectionHeader title="전체 업종 등락률" sub={`총 ${data.sectors.length}개 업종`} />
        <div className="space-y-0.5">
          {data.sectors.map(s => (
            <SectorBar key={s.name} sector={s} maxAbs={maxAbs} />
          ))}
        </div>
      </Card>

      {/* 보합 섹터 */}
      {data.flat.length > 0 && (
        <Card className="p-5">
          <SectionHeader title="보합 섹터" sub="±0.5% 이내" />
          <div className="flex flex-wrap gap-2">
            {data.flat.map(s => (
              <div key={s.name} className="flex items-center gap-1 bg-slate-50 rounded-lg px-2.5 py-1">
                <Minus size={11} className="text-slate-400" />
                <span className="text-xs text-slate-500">{s.name}</span>
                <span className="text-xs text-slate-400">{fmtChange(s.change)}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
