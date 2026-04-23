export function fmtKrw(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toLocaleString('ko-KR')}원`
}

export function fmtUsd(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}$${value.toLocaleString('en-US')}`
}

export function fmtAmount(value: number, currency: string): string {
  return currency === 'USD' ? fmtUsd(value) : fmtKrw(value)
}

export function fmtRate(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

export function colorClass(value: number): string {
  if (value > 0) return 'text-red-500'
  if (value < 0) return 'text-blue-500'
  return 'text-slate-500'
}

export const MONTHS = Array.from({ length: 12 }, (_, i) => `${i + 1}월`)
