import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Bot,
  FileText,
  Play,
  Power,
  RefreshCw,
  Save,
  ShieldCheck,
} from 'lucide-react'
import { Card, SectionHeader } from '../components/Card'
import { apiJson, apiPatchJson, apiPostJson } from '../lib/api'

interface TradingConfig {
  enabled: boolean
  dry_run: boolean
  strategy_name: string
  open_scan_time: string
  scan_end_time: string
  universe_top_n: number
  candidate_limit: number
  capital_krw: number
  max_positions: number
  per_trade_budget_krw: number
  min_stock_price_krw: number
  max_stock_price_krw: number
  min_trade_value_krw: number
  min_intraday_range_pct: number
  min_change_pct: number
  buy_split_pct: number[]
  add_buy_pullback_pct: number
  add_buy_breakout_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  sell_split_pct: number[]
  first_take_profit_pct: number
  second_take_profit_pct: number
  trailing_stop_pct: number
  force_exit_time: string
  cooldown_minutes: number
  last_open_scan_date: string
}

interface KisStatus {
  configured: boolean
  mock: boolean
  base_url: string
  account_configured: boolean
  live_orders_enabled: boolean
  token_cached: boolean
}

interface Candidate {
  code: string
  name: string
  price: number
  change_pct: number
  trade_value_krw: number
  intraday_range_pct: number
  score: number
  signal: 'BUY' | 'WATCH'
  decision: string
  reason: string
  source: string
}

interface PlannedOrder {
  side: 'BUY' | 'SELL'
  code: string
  name: string
  budget_krw: number
  quantity: number
  buy_plan: { leg: number; label: string; trigger: string; budget_krw: number; quantity: number }[]
  sell_plan: { leg: number; trigger: string; quantity: number }[]
  stop_loss_pct: number
  force_exit_time: string
  reason: string
  dry_run: boolean
}

interface TradingRun {
  id: string
  ran_at: string
  mode: string
  warnings: string[]
  candidates: Candidate[]
  planned_orders: PlannedOrder[]
}

interface TradingStatus {
  config: TradingConfig
  kis: KisStatus
  latest_run: TradingRun | null
  runs_count: number
  rules: string
  journal_date: string
  journal_dates: string[]
  journal_tail: string
}

interface TradingJournal {
  date: string | null
  dates: string[]
  content: string
}

const won = (value: number) => `${value.toLocaleString('ko-KR')}원`
const pct = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
const splitText = (values: number[]) => values.join('/')

export default function TradingBot() {
  const [status, setStatus] = useState<TradingStatus | null>(null)
  const [rules, setRules] = useState('')
  const [savingRules, setSavingRules] = useState(false)
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [selectedJournalDate, setSelectedJournalDate] = useState('')

  const load = useCallback(async () => {
    const data = await apiJson<TradingStatus>('/api/trading/status', 15000)
    setStatus(data)
    setRules(data.rules)
    setSelectedJournalDate(data.journal_date)
  }, [])

  useEffect(() => {
    load().catch(e => setMessage(e instanceof Error ? e.message : '자동매매 상태를 불러오지 못했습니다.'))
  }, [load])

  const patchConfig = async (patch: Partial<TradingConfig>) => {
    const data = await apiPatchJson<TradingStatus>('/api/trading/config', patch, 15000)
    setStatus(data)
    setRules(data.rules)
  }

  const runScan = async () => {
    setRunning(true)
    setMessage(null)
    try {
      const data = await apiPostJson<TradingStatus>('/api/trading/open-scan', undefined, 30000)
      setStatus(data)
      setRules(data.rules)
      setSelectedJournalDate(data.journal_date)
      setMessage('장 시작 스캔을 실행하고 판단 이유를 저널에 남겼습니다.')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '스캔 실행에 실패했습니다.')
    } finally {
      setRunning(false)
    }
  }

  const loadJournal = async (date: string) => {
    const data = await apiJson<TradingJournal>(`/api/trading/journal?date=${encodeURIComponent(date)}`, 15000)
    setStatus(prev => prev ? { ...prev, journal_date: date, journal_dates: data.dates, journal_tail: data.content } : prev)
    setSelectedJournalDate(date)
  }

  const saveRules = async () => {
    setSavingRules(true)
    setMessage(null)
    try {
      await apiPostJson<{ content: string }>('/api/trading/rules', { content: rules }, 15000)
      await load()
      setMessage('매매 원칙을 Markdown 파일에 저장했습니다.')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : '매매 원칙 저장에 실패했습니다.')
    } finally {
      setSavingRules(false)
    }
  }

  const latestCandidates = useMemo(() => status?.latest_run?.candidates ?? [], [status])
  const plannedOrders = status?.latest_run?.planned_orders ?? []

  if (!status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const config = status.config
  const inputClass = 'w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white'

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">급등주 스캘핑 자동매매</h1>
          <p className="text-sm text-slate-400 mt-1">장 초반 급등주를 스캔하고 날짜별 매매일지에 판단 이유를 기록합니다.</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => load()}
            className="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:text-slate-800"
            title="새로고침"
          >
            <RefreshCw size={16} />
          </button>
          <button
            onClick={runScan}
            disabled={running}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Play size={15} />
            {running ? '스캔 중' : '지금 스캔'}
          </button>
        </div>
      </div>

      {message && (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          {message}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <Card className="p-5">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase">
            <Power size={15} />
            운용 상태
          </div>
          <button
            onClick={() => patchConfig({ enabled: !config.enabled })}
            className={`mt-3 w-full rounded-lg px-3 py-2 text-sm font-bold ${
              config.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
            }`}
          >
            {config.enabled ? '자동 스캔 켜짐' : '자동 스캔 꺼짐'}
          </button>
          <p className="mt-2 text-xs text-slate-400">신규 진입 관찰 {config.open_scan_time}~{config.scan_end_time}</p>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase">
            <ShieldCheck size={15} />
            주문 모드
          </div>
          <button
            onClick={() => patchConfig({ dry_run: !config.dry_run })}
            className={`mt-3 w-full rounded-lg px-3 py-2 text-sm font-bold ${
              config.dry_run ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
            }`}
          >
            {config.dry_run ? 'Dry-run' : '실주문 준비'}
          </button>
          <p className="mt-2 text-xs text-slate-400">
            실주문은 KIS_ENABLE_LIVE_ORDERS=true일 때만 해제됩니다.
          </p>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase">
            <Bot size={15} />
            KIS 연결
          </div>
          <p className={`mt-3 text-lg font-bold ${status.kis.configured ? 'text-emerald-600' : 'text-slate-400'}`}>
            {status.kis.configured ? '설정됨' : '미설정'}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {status.kis.mock ? '모의투자 URL' : '실전투자 URL'} · 토큰 {status.kis.token_cached ? '캐시됨' : '없음'}
          </p>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2 text-slate-500 text-xs font-semibold uppercase">
            <FileText size={15} />
            기록
          </div>
          <p className="mt-3 text-lg font-bold text-slate-800">{status.runs_count}회</p>
          <p className="mt-1 text-xs text-slate-400">
            날짜별 일지 {status.journal_dates.length}개
          </p>
        </Card>
      </div>

      {!status.kis.configured && (
        <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle size={17} className="mt-0.5 shrink-0" />
          <p>KIS 인증 정보가 없어서 스캔은 데모 급등 후보로 동작합니다. `.env`에 KIS_APP_KEY 또는 MYAPP, KIS_APP_SECRET 또는 MYSEC를 넣으면 한국투자증권 데이터를 먼저 사용합니다.</p>
        </div>
      )}

      <Card className="p-5">
        <SectionHeader title="전략 설정" sub="초기값은 보수적으로 잡아두었습니다." />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <label className="text-xs font-medium text-slate-500">
            관찰 시작
            <input className={`${inputClass} mt-1`} value={config.open_scan_time} onChange={e => patchConfig({ open_scan_time: e.target.value })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            관찰 종료
            <input className={`${inputClass} mt-1`} value={config.scan_end_time} onChange={e => patchConfig({ scan_end_time: e.target.value })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            후보 상위 N
            <input className={`${inputClass} mt-1`} type="number" value={config.universe_top_n} onChange={e => patchConfig({ universe_top_n: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            총 실험 자금
            <input className={`${inputClass} mt-1`} type="number" value={config.capital_krw} onChange={e => patchConfig({ capital_krw: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            1회 예산
            <input className={`${inputClass} mt-1`} type="number" value={config.per_trade_budget_krw} onChange={e => patchConfig({ per_trade_budget_krw: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            최대 보유
            <input className={`${inputClass} mt-1`} type="number" value={config.max_positions} onChange={e => patchConfig({ max_positions: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            최소 주가
            <input className={`${inputClass} mt-1`} type="number" value={config.min_stock_price_krw} onChange={e => patchConfig({ min_stock_price_krw: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            최대 주가
            <input className={`${inputClass} mt-1`} type="number" value={config.max_stock_price_krw} onChange={e => patchConfig({ max_stock_price_krw: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            최소 거래대금
            <input className={`${inputClass} mt-1`} type="number" value={config.min_trade_value_krw} onChange={e => patchConfig({ min_trade_value_krw: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            최소 변동폭 %
            <input className={`${inputClass} mt-1`} type="number" step="0.1" value={config.min_intraday_range_pct} onChange={e => patchConfig({ min_intraday_range_pct: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            최소 급등률 %
            <input className={`${inputClass} mt-1`} type="number" step="0.1" value={config.min_change_pct} onChange={e => patchConfig({ min_change_pct: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            손절 %
            <input className={`${inputClass} mt-1`} type="number" step="0.1" value={config.stop_loss_pct} onChange={e => patchConfig({ stop_loss_pct: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            분할매수 %
            <input
              className={`${inputClass} mt-1`}
              value={splitText(config.buy_split_pct)}
              onChange={e => patchConfig({ buy_split_pct: e.target.value.split('/').map(Number).filter(Number.isFinite) })}
            />
          </label>
          <label className="text-xs font-medium text-slate-500">
            눌림 추가 %
            <input className={`${inputClass} mt-1`} type="number" step="0.1" value={config.add_buy_pullback_pct} onChange={e => patchConfig({ add_buy_pullback_pct: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            돌파 추가 %
            <input className={`${inputClass} mt-1`} type="number" step="0.1" value={config.add_buy_breakout_pct} onChange={e => patchConfig({ add_buy_breakout_pct: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            분할매도 %
            <input
              className={`${inputClass} mt-1`}
              value={splitText(config.sell_split_pct)}
              onChange={e => patchConfig({ sell_split_pct: e.target.value.split('/').map(Number).filter(Number.isFinite) })}
            />
          </label>
          <label className="text-xs font-medium text-slate-500">
            1차 익절 %
            <input className={`${inputClass} mt-1`} type="number" step="0.1" value={config.first_take_profit_pct} onChange={e => patchConfig({ first_take_profit_pct: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            2차 익절 %
            <input className={`${inputClass} mt-1`} type="number" step="0.1" value={config.second_take_profit_pct} onChange={e => patchConfig({ second_take_profit_pct: Number(e.target.value) })} />
          </label>
          <label className="text-xs font-medium text-slate-500">
            당일청산 시각
            <input className={`${inputClass} mt-1`} value={config.force_exit_time} onChange={e => patchConfig({ force_exit_time: e.target.value })} />
          </label>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionHeader title="주문 계획" sub={status.latest_run ? status.latest_run.ran_at : '아직 실행 없음'} />
          {plannedOrders.length === 0 ? (
            <p className="text-sm text-slate-400">현재 매수 후보가 없습니다.</p>
          ) : plannedOrders.map(order => (
            <div key={`${order.code}-${order.side}`} className="border-b border-slate-100 py-3 last:border-0">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-bold text-slate-800">{order.name} <span className="text-xs text-slate-400">{order.code}</span></p>
                  <p className="text-xs text-slate-400 mt-1">{order.reason}</p>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-slate-500">
                    <div className="rounded-lg bg-slate-50 p-2">
                      <p className="font-bold text-slate-700 mb-1">분할매수</p>
                      {order.buy_plan.map(leg => (
                        <p key={leg.leg}>{leg.leg}차 {leg.quantity}주 · {won(leg.budget_krw)} · {leg.trigger}</p>
                      ))}
                    </div>
                    <div className="rounded-lg bg-slate-50 p-2">
                      <p className="font-bold text-slate-700 mb-1">분할매도/손절</p>
                      {order.sell_plan.map(leg => (
                        <p key={leg.leg}>{leg.leg}차 {leg.quantity}주 · {leg.trigger}</p>
                      ))}
                      <p>손절 {order.stop_loss_pct}% · {order.force_exit_time} 청산 후보</p>
                    </div>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-sm font-bold text-red-500">{order.quantity}주</p>
                  <p className="text-xs text-slate-400">{won(order.budget_krw)}</p>
                </div>
              </div>
            </div>
          ))}
        </Card>

        <Card className="p-5 overflow-x-auto">
          <SectionHeader title="후보 랭킹" sub="점수는 거래대금, 변동폭, 상승률을 합산합니다." />
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400">
                <th className="py-2 text-left">종목</th>
                <th className="py-2 text-right">등락률</th>
                <th className="py-2 text-right">변동폭</th>
                <th className="py-2 text-right">거래대금</th>
                <th className="py-2 text-right">판단</th>
              </tr>
            </thead>
            <tbody>
              {latestCandidates.map(candidate => (
                <tr key={candidate.code} className="border-b border-slate-50 last:border-0">
                  <td className="py-2">
                    <p className="font-semibold text-slate-700">{candidate.name}</p>
                    <p className="text-xs text-slate-400">{candidate.code} · {candidate.source}</p>
                  </td>
                  <td className={`py-2 text-right font-semibold ${candidate.change_pct >= 0 ? 'text-red-500' : 'text-blue-500'}`}>{pct(candidate.change_pct)}</td>
                  <td className="py-2 text-right text-slate-600">{candidate.intraday_range_pct.toFixed(2)}%</td>
                  <td className="py-2 text-right text-slate-600">{won(candidate.trade_value_krw)}</td>
                  <td className="py-2 text-right">
                    <span className={`rounded-full px-2 py-1 text-xs font-bold ${candidate.signal === 'BUY' ? 'bg-red-50 text-red-600' : 'bg-slate-100 text-slate-500'}`}>
                      {candidate.decision}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <SectionHeader title="매매 원칙 Markdown" sub="data/trading_rules.md" />
            <button
              onClick={saveRules}
              disabled={savingRules}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <Save size={14} />
              저장
            </button>
          </div>
          <textarea
            className="h-80 w-full resize-none rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={rules}
            onChange={e => setRules(e.target.value)}
          />
        </Card>

        <Card className="p-5">
          <SectionHeader title="판단 이유 저널" sub="날짜별 매매일지" />
          <div className="mb-3 flex items-center gap-2">
            <select
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-400"
              value={selectedJournalDate}
              onChange={e => loadJournal(e.target.value)}
            >
              {status.journal_dates.map(date => (
                <option key={date} value={date}>{date}</option>
              ))}
            </select>
            <span className="text-xs text-slate-400">data/trading_journal/{selectedJournalDate}.md</span>
          </div>
          <pre className="h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950 p-4 text-xs leading-relaxed text-slate-100">
            {status.journal_tail}
          </pre>
        </Card>
      </div>
    </div>
  )
}
