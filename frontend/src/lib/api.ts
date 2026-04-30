const BACKEND_PORT = '8001'

function apiBase(): string {
  if (typeof window === 'undefined') return ''
  return `${window.location.protocol}//${window.location.hostname}:${BACKEND_PORT}`
}

export async function apiJson<T>(path: string, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(`${apiBase()}${path}`, { signal: controller.signal })
    if (!res.ok) throw new Error(`API ${res.status}: ${path}`)
    return await res.json()
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`API timeout: ${path}`)
    }
    throw error
  } finally {
    window.clearTimeout(timer)
  }
}
