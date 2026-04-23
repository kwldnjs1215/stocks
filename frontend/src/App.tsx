import { useState } from 'react'
import { LayoutDashboard, TrendingUp, ArrowLeftRight, BarChart2, Newspaper, Activity } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import TradeInput from './pages/TradeInput'
import CashFlow from './pages/CashFlow'
import Analytics from './pages/Analytics'
import MarketOverview from './pages/MarketOverview'
import SectorTrend from './pages/SectorTrend'

const PAGES = [
  { id: 'dashboard', label: '대시보드', icon: LayoutDashboard },
  { id: 'market', label: '시황', icon: Newspaper },
  { id: 'trend', label: '섹터 추이', icon: Activity },
  { id: 'trade', label: '매매 입력', icon: TrendingUp },
  { id: 'cashflow', label: '입출금', icon: ArrowLeftRight },
  { id: 'analytics', label: '분석', icon: BarChart2 },
] as const

type PageId = typeof PAGES[number]['id']

export default function App() {
  const [page, setPage] = useState<PageId>('dashboard')
  const [refreshKey, setRefreshKey] = useState(0)

  const handleDataUpdate = () => setRefreshKey(k => k + 1)

  return (
    <div className="flex h-screen bg-slate-100">
      <aside className="w-56 bg-slate-900 flex flex-col shrink-0">
        <div className="px-5 py-6 border-b border-slate-700">
          <div className="text-white font-bold text-lg leading-tight">주식 대시보드</div>
          <div className="text-slate-400 text-xs mt-1">김지원</div>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {PAGES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                page === id
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              <Icon size={17} />
              {label}
            </button>
          ))}
        </nav>
        <div className="px-5 py-4 border-t border-slate-700">
          <p className="text-slate-500 text-xs">2021 – 2026</p>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-6 py-8">
          {page === 'dashboard' && <Dashboard refreshKey={refreshKey} />}
          {page === 'market' && <MarketOverview />}
          {page === 'trend' && <SectorTrend />}
          {page === 'trade' && <TradeInput onDataUpdate={handleDataUpdate} />}
          {page === 'cashflow' && <CashFlow onDataUpdate={handleDataUpdate} />}
          {page === 'analytics' && <Analytics refreshKey={refreshKey} />}
        </div>
      </main>
    </div>
  )
}
