'use client'

import { useState, useEffect } from 'react'
import {
  Activity,
  Brain,
  Database,
  Globe,
  FolderOpen,
  Terminal,
  GitBranch,
  Cpu,
  CheckSquare,
  StickyNote,
  Bell,
  MessageSquare,
  Loader2,
  Server,
  Zap,
  Clock,
  CheckCircle2,
  AlertCircle,
  WifiOff,
} from 'lucide-react'
import { statusApi, type AgentStatus } from '@/services/api'
import { cn } from '@/lib/utils'

const capabilityIcons: Record<string, React.ElementType> = {
  Globe,
  FolderOpen,
  Terminal,
  GitBranch,
  Brain,
  Database,
}

function StatusBadge({ status }: { status: AgentStatus['memoryStatus']['status'] }) {
  const config = {
    healthy: { label: '正常', icon: CheckCircle2, cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
    degraded: { label: '降级', icon: AlertCircle, cls: 'bg-amber-50 text-amber-700 border-amber-200' },
    offline: { label: '离线', icon: WifiOff, cls: 'bg-red-50 text-red-600 border-red-200' },
  }[status]

  const Icon = config.icon
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium', config.cls)}>
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  )
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent = false,
}: {
  label: string
  value: string | number
  sub?: string
  icon: React.ElementType
  accent?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-xl border bg-card p-5 shadow-sm transition-shadow hover:shadow-md',
        accent ? 'border-primary/30' : 'border-border',
      )}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          <p className={cn('mt-1.5 text-2xl font-bold', accent ? 'text-primary' : 'text-foreground')}>
            {value}
          </p>
          {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
        </div>
        <div
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-lg',
            accent ? 'bg-primary/10' : 'bg-muted',
          )}
        >
          <Icon className={cn('h-5 w-5', accent ? 'text-primary' : 'text-muted-foreground')} />
        </div>
      </div>
    </div>
  )
}

function CapabilityCard({ name, description, icon }: { name: string; description: string; icon: string }) {
  const Icon = capabilityIcons[icon] ?? Zap
  return (
    <div className="flex gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <Icon className="h-4.5 w-4.5 h-[18px] w-[18px] text-primary" />
      </div>
      <div>
        <p className="text-sm font-semibold text-foreground">{name}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>
      </div>
    </div>
  )
}

export default function StatusPage() {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date())
  const [refreshing, setRefreshing] = useState(false)

  const loadStatus = async () => {
    setRefreshing(true)
    const data = await statusApi.get()
    setStatus(data)
    setLastRefreshed(new Date())
    setLoading(false)
    setRefreshing(false)
  }

  useEffect(() => {
    loadStatus()
  }, [])

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <header className="flex h-14 items-center justify-between border-b border-border bg-card px-5">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          <h1 className="text-sm font-semibold">系统状态</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-muted-foreground">
            上次刷新：{lastRefreshed.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <button
            onClick={loadStatus}
            disabled={refreshing}
            className="flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors"
          >
            {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Activity className="h-3.5 w-3.5" />}
            刷新
          </button>
        </div>
      </header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : status ? (
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="mx-auto max-w-5xl space-y-8">

            {/* Agent Info Banner */}
            <div className="flex items-center justify-between rounded-xl border border-primary/20 bg-primary/5 px-5 py-4">
              <div className="flex items-center gap-4">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/15">
                  <Cpu className="h-5.5 w-5.5 h-[22px] w-[22px] text-primary" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {status.provider} · {status.model}
                  </p>
                  <p className="text-xs text-muted-foreground">版本 {status.version} · 运行时长 {status.uptime}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs font-medium text-emerald-600">运行中</span>
              </div>
            </div>

            {/* Personal Data Stats */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                个人数据概览
              </h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <StatCard
                  label="待办事项"
                  value={status.personalData.todos}
                  sub={`${status.personalData.completedTodos} 已完成`}
                  icon={CheckSquare}
                />
                <StatCard
                  label="笔记"
                  value={status.personalData.notes}
                  icon={StickyNote}
                />
                <StatCard
                  label="提醒"
                  value={status.personalData.reminders}
                  icon={Bell}
                />
                <StatCard
                  label="历史会话"
                  value={status.personalData.sessions}
                  icon={MessageSquare}
                />
                <StatCard
                  label="向量记忆"
                  value={status.memoryStatus.vectorCount.toLocaleString()}
                  sub="条嵌入向量"
                  icon={Brain}
                  accent
                />
              </div>
            </section>

            {/* Memory Status */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                向量记忆 (ChromaDB)
              </h2>
              <div className="rounded-xl border border-border bg-card shadow-sm">
                <div className="grid divide-y divide-border sm:grid-cols-2 sm:divide-x sm:divide-y-0">
                  <div className="flex items-center justify-between px-5 py-4">
                    <div className="flex items-center gap-3">
                      <Database className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">集合名称</p>
                        <p className="mt-0.5 font-mono text-sm font-medium text-foreground">
                          {status.memoryStatus.collectionName}
                        </p>
                      </div>
                    </div>
                    <StatusBadge status={status.memoryStatus.status} />
                  </div>
                  <div className="flex items-center gap-3 px-5 py-4">
                    <Brain className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">嵌入模型</p>
                      <p className="mt-0.5 font-mono text-sm font-medium text-foreground">
                        {status.memoryStatus.embeddingModel}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="border-t border-border px-5 py-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">向量条数</span>
                    <div className="flex items-center gap-3">
                      <div className="h-1.5 w-32 overflow-hidden rounded-full bg-muted">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${Math.min((status.memoryStatus.vectorCount / 5000) * 100, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-foreground">
                        {status.memoryStatus.vectorCount.toLocaleString()} / 5,000
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Model Info */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                模型信息
              </h2>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl border border-border bg-card px-5 py-4 shadow-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Server className="h-4 w-4" />
                    <p className="text-xs">模型</p>
                  </div>
                  <p className="mt-1.5 text-sm font-semibold text-foreground">{status.model}</p>
                </div>
                <div className="rounded-xl border border-border bg-card px-5 py-4 shadow-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Zap className="h-4 w-4" />
                    <p className="text-xs">提供商</p>
                  </div>
                  <p className="mt-1.5 text-sm font-semibold text-foreground">{status.provider}</p>
                </div>
                <div className="rounded-xl border border-border bg-card px-5 py-4 shadow-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Clock className="h-4 w-4" />
                    <p className="text-xs">运行时长</p>
                  </div>
                  <p className="mt-1.5 text-sm font-semibold text-foreground">{status.uptime}</p>
                </div>
              </div>
            </section>

            {/* Capabilities */}
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                可用能力 ({status.capabilities.length})
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {status.capabilities.map((cap) => (
                  <CapabilityCard key={cap.name} {...cap} />
                ))}
              </div>
            </section>

          </div>
        </div>
      ) : null}
    </div>
  )
}
