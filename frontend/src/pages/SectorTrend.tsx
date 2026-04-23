import { useEffect, useState, useCallback } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import {
  LineChart, Line, ResponsiveContainer, Tooltip, YAxis,
} from 'recharts'
import { Card, SectionHeader } from '../components/Card'

interface SparkPoint {
  date: string
  close: number
  r: number
}

interface SectorData {
  sector: string
  etf: string
  code: string
  price: number
  change_1d: number
  change_5d: number
  change_20d: number
  from_high: number
  streak: number
  momentum: '상승' | '하락' | '횡보'
  comment: string
  sparkline: SparkPoint[]
}

interface TrendData {
  sectors: SectorData[]
  updated_at: string
}

function fmtChange(v: number) {
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function MomentumBadge({ m }: { m: SectorData['momentum'] }) {
  const cfg = {
    상승: { cls: 'bg-red-50 text-red-500 border border-red-200', icon: <TrendingUp size={11} /> },
    하락: { cls: 'bg-blue-50 text-blue-500 border border-blue-200', icon: <TrendingDown size={11} /> },
    횡보: { cls: 'bg-slate-50 text-slate-400 border border-slate-200', icon: <Minus size={11} /> },
  }[m]
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.cls}`}>
      {cfg.icon}{m}
    </span>
  )
}

function StatBox({ label, value, up }: { label: string; value: number; up?: boolean }) {
  const color = value > 0 ? 'text-red-500' : value < 0 ? 'text-blue-500' : 'text-slate-400'
  return (
    <div className="text-center">
      <p className="text-[10px] text-slate-400 mb-0.5">{label}</p>
      <p className={`text-xs font-bold ${color}`}>{fmtChange(value)}</p>
    </div>
  )
}

const CustomDot = () => null

function Sparkline({ data, momentum }: { data: SparkPoint[]; momentum: SectorData['momentum'] }) {
  const color = momentum === '상승' ? '#ef4444' : momentum === '하락' ? '#3b82f6' : '#94a3b8'
  return (
    <ResponsiveContainer width="100%" height={64}>
      <LineChart data={data} margin={{ top: 4, right: 2, left: 2, bottom: 4 }}>
        <YAxis domain={['auto', 'auto']} hide />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const d = payload[0].payload as SparkPoint
            return (
              <div className="bg-white border border-slate-100 rounded-lg px-2 py-1 shadow text-[10px]">
                <p className="text-slate-400">{d.date}</p>
                <p className="font-semibold text-slate-700">{d.close.toLocaleString()}</p>
                <p className={d.r >= 0 ? 'text-red-500' : 'text-blue-500'}>{fmtChange(d.r)}</p>
              </div>
            )
          }}
        />
        <Line
          type="monotone"
          dataKey="close"
          stroke={color}
          strokeWidth={1.5}
          dot={<CustomDot />}
          activeDot={{ r: 3, fill: color }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

function StreakBar({ streak }: { streak: number }) {
  const days = Math.abs(streak)
  const isUp = streak > 0
  if (days < 2) return null
  return (
    <div className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${isUp ? 'bg-red-50 text-red-400' : 'bg-blue-50 text-blue-400'}`}>
      {isUp ? '▲' : '▼'} {days}일 연속
    </div>
  )
}

function SectorCard({ s }: { s: SectorData }) {
  return (
    <Card className="p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-bold text-slate-800">{s.sector}</p>
          <p className="text-[10px] text-slate-400 mt-0.5">{s.etf}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <MomentumBadge m={s.momentum} />
          <StreakBar streak={s.streak} />
        </div>
      </div>

      <Sparkline data={s.sparkline} momentum={s.momentum} />

      <div className="grid grid-cols-3 gap-1 border-t border-slate-50 pt-2">
        <StatBox label="오늘" value={s.change_1d} />
        <StatBox label="5일" value={s.change_5d} />
        <StatBox label="20일" value={s.change_20d} />
      </div>

      {s.comment && (
        <p className="text-[11px] text-slate-400 border-t border-slate-50 pt-2 leading-relaxed">
          {s.comment}
          {s.from_high < -3 && (
            <span className="ml-1 text-blue-400">
              · 고점 대비 {Math.abs(s.from_high).toFixed(1)}%
            </span>
          )}
        </p>
      )}
    </Card>
  )
}

function SummaryRow({ sectors }: { sectors: SectorData[] }) {
  const rising = sectors.filter(s => s.momentum === '상승')
  const falling = sectors.filter(s => s.momentum === '하락')
  const flat = sectors.filter(s => s.momentum === '횡보')
  const hotStreak = sectors.reduce((a, b) => Math.abs(b.streak) > Math.abs(a.streak) ? b : a, sectors[0])

  return (
    <div className="grid grid-cols-4 gap-3">
      <Card className="p-4 text-center">
        <p className="text-xs text-slate-400 mb-1">상승 추세</p>
        <p className="text-2xl font-bold text-red-500">{rising.length}</p>
        <p className="text-[10px] text-slate-400 mt-1">{rising.map(s => s.sector).join(', ') || '-'}</p>
      </Card>
      <Card className="p-4 text-center">
        <p className="text-xs text-slate-400 mb-1">하락 추세</p>
        <p className="text-2xl font-bold text-blue-500">{falling.length}</p>
        <p className="text-[10px] text-slate-400 mt-1">{falling.map(s => s.sector).join(', ') || '-'}</p>
      </Card>
      <Card className="p-4 text-center">
        <p className="text-xs text-slate-400 mb-1">횡보</p>
        <p className="text-2xl font-bold text-slate-400">{flat.length}</p>
        <p className="text-[10px] text-slate-400 mt-1">{flat.map(s => s.sector).join(', ') || '-'}</p>
      </Card>
      <Card className="p-4 text-center">
        <p className="text-xs text-slate-400 mb-1">연속 최강</p>
        <p className="text-lg font-bold text-slate-700">{hotStreak?.sector ?? '-'}</p>
        <p className={`text-[10px] font-semibold mt-1 ${hotStreak?.streak > 0 ? 'text-red-400' : 'text-blue-400'}`}>
          {hotStreak ? `${Math.abs(hotStreak.streak)}일 연속 ${hotStreak.streak > 0 ? '상승' : '하락'}` : ''}
        </p>
      </Card>
    </div>
  )
}

export default function SectorTrend() {
  const [data, setData] = useState<TrendData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [sort, setSort] = useState<'5d' | '1d' | '20d' | 'streak'>('5d')

  const load = useCallback(async (forceRefresh = false) => {
    try {
      if (forceRefresh) setRefreshing(true)
      else setLoading(true)
      setError(null)
      const url = forceRefresh ? '/api/sector-trend/refresh' : '/api/sector-trend'
      const resp = await fetch(url, { method: forceRefresh ? 'POST' : 'GET' })
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

  const sorted = data
    ? [...data.sectors].sort((a, b) => {
        if (sort === '5d') return b.change_5d - a.change_5d
        if (sort === '1d') return b.change_1d - a.change_1d
        if (sort === '20d') return b.change_20d - a.change_20d
        return Math.abs(b.streak) - Math.abs(a.streak)
      })
    : []

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <div className="text-slate-400 text-sm">ETF 데이터 수집 중... (최초 10~20초)</div>
        <div className="text-slate-300 text-xs">TIGER 반도체, 2차전지, 방산 등 10개 섹터</div>
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-800">섹터 추이</h1>
          <p className="text-xs text-slate-400 mt-0.5">업데이트: {data.updated_at} · 최근 20거래일 ETF 기준</p>
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

      {sorted.length > 0 && <SummaryRow sectors={sorted} />}

      <div className="flex items-center gap-2">
        <span className="text-xs text-slate-400">정렬:</span>
        {(['5d', '1d', '20d', 'streak'] as const).map(k => (
          <button
            key={k}
            onClick={() => setSort(k)}
            className={`text-xs px-2.5 py-1 rounded-lg border transition ${
              sort === k
                ? 'bg-blue-600 text-white border-blue-600'
                : 'text-slate-500 border-slate-200 hover:bg-slate-50'
            }`}
          >
            {{ '5d': '5일 수익률', '1d': '오늘', '20d': '20일', 'streak': '연속일수' }[k]}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {sorted.map(s => <SectorCard key={s.sector} s={s} />)}
      </div>
    </div>
  )
}
