'use client'

import { useEffect, useRef, useState } from 'react'
import { BellRing } from 'lucide-react'
import { remindersApi, type FiredReminder } from '@/services/api'

const POLL_MS = 8000

/**
 * 全屏提醒遮罩：轮询后端"已触发提醒"事件，
 * 触发时弹全屏遮罩，需点击"确认"后才关闭。
 */
export default function ReminderOverlay() {
  const [queue, setQueue] = useState<FiredReminder[]>([])
  const lastTsRef = useRef<number>(Date.now() / 1000)

  useEffect(() => {
    let cancelled = false

    const tick = async () => {
      try {
        const events = await remindersApi.fired(lastTsRef.current)
        if (cancelled || events.length === 0) return
        lastTsRef.current = Math.max(lastTsRef.current, ...events.map((e) => e.ts))
        setQueue((q) => [...q, ...events])
      } catch {
        // 后端未启动 / 网络异常时静默跳过，下个周期再试
      }
    }

    void tick()
    const timer = window.setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const current = queue[0]
  if (!current) return null

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 p-6">
      <div className="fade-in-up w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-2xl">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-100">
          <BellRing className="h-7 w-7 text-amber-600" />
        </div>
        <h2 className="text-lg font-semibold text-foreground">提醒</h2>
        <p className="mt-3 text-xl font-medium leading-relaxed text-foreground">{current.text}</p>
        {current.when != null && (
          <p className="mt-2 text-sm text-muted-foreground">
            预定时间 {new Date(current.when * 1000).toLocaleString('zh-CN')}
          </p>
        )}
        <button
          onClick={() => setQueue((q) => q.slice(1))}
          className="mt-6 w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          知道了，继续
        </button>
      </div>
    </div>
  )
}