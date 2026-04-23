import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
}

export function Card({ children, className = '' }: CardProps) {
  return (
    <div className={`bg-white rounded-2xl shadow-sm border border-slate-100 ${className}`}>
      {children}
    </div>
  )
}

interface KpiCardProps {
  label: string
  value: string
  sub?: string
  valueClass?: string
}

export function KpiCard({ label, value, sub, valueClass = 'text-slate-800' }: KpiCardProps) {
  return (
    <Card className="p-5">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
      <p className={`text-2xl font-bold mt-1.5 ${valueClass}`}>{value}</p>
      {sub && <p className="text-xs text-slate-400 mt-1.5">{sub}</p>}
    </Card>
  )
}

interface SectionHeaderProps {
  title: string
  sub?: string
}

export function SectionHeader({ title, sub }: SectionHeaderProps) {
  return (
    <div className="mb-4">
      <h2 className="text-base font-bold text-slate-800">{title}</h2>
      {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
    </div>
  )
}

export function Divider() {
  return <div className="border-t border-slate-100 my-6" />
}
