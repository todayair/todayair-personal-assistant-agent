'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  MessageSquare,
  CheckSquare,
  FileText,
  Bell,
  CalendarDays,
  Mail,
  Clock,
  Activity,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItem {
  href: string
  label: string
  icon: LucideIcon
  description: string
  group: string
}

const navItems: NavItem[] = [
  { href: '/chat', label: '对话', icon: MessageSquare, description: 'AI 聊天', group: '核心' },
  { href: '/todos', label: '待办', icon: CheckSquare, description: '任务管理', group: '核心' },
  { href: '/calendar', label: '日历', icon: CalendarDays, description: '日程计划', group: '核心' },
  { href: '/notes', label: '笔记', icon: FileText, description: '知识记录', group: '知识' },
  { href: '/reminders', label: '提醒', icon: Bell, description: '定时提醒', group: '知识' },
  { href: '/mail', label: '邮箱', icon: Mail, description: '邮件收发', group: '工具' },
  { href: '/history', label: '历史', icon: Clock, description: '会话记录', group: '工具' },
  { href: '/status', label: '状态', icon: Activity, description: '系统概览', group: '工具' },
]

const groupLabels: Record<string, string> = {
  '核心': '工作区',
  '知识': '知识库',
  '工具': '工具',
}

const groupOrder = ['核心', '知识', '工具']

export function Sidebar() {
  const pathname = usePathname()

  const grouped = groupOrder.map((g) => ({
    group: g,
    items: navItems.filter((i) => i.group === g),
  }))

  return (
    <aside className="flex h-full w-56 flex-col bg-sidebar text-sidebar-foreground">
      {/* Logo / Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-sidebar-border px-4">
        <div className="relative h-8 w-8">
          <img
            src="/logo.svg"
            alt="AI 助手标志"
            className="h-8 w-8 rounded-lg object-cover shadow-md shadow-primary/30"
          />
          <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-400 ring-2 ring-sidebar" />
        </div>
        <div className="flex flex-1 items-center justify-center leading-none">
          <span className="font-rokkitt text-lg font-semibold tracking-tight text-sidebar-accent-foreground">
            todayair's agent
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3" aria-label="主导航">
        {grouped.map(({ group, items }) => (
          <div key={group} className="mb-1">
            <p className="px-4 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-widest text-sidebar-foreground/35">
              {groupLabels[group]}
            </p>
            <ul className="space-y-0.5 px-2">
              {items.map(({ href, label, icon: Icon }) => {
                const isActive = pathname === href || pathname.startsWith(href + '/')
                return (
                  <li key={href}>
                    <Link
                      href={href}
                      className={cn(
                        'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all duration-200',
                        isActive
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                          : 'text-sidebar-foreground/80 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground',
                      )}
                      aria-current={isActive ? 'page' : undefined}
                    >
                      {/* Active indicator bar */}
                      <span
                        className={cn(
                          'absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-primary transition-all duration-300',
                          isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-30',
                        )}
                      />
                      <Icon
                        className={cn(
                          'h-4 w-4 shrink-0 transition-colors',
                          isActive
                            ? 'text-primary'
                            : 'text-sidebar-foreground/50 group-hover:text-sidebar-foreground',
                        )}
                      />
                      <span className="flex-1">{label}</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <span className="text-[11px] text-sidebar-foreground/50">在线 · v1.0</span>
        </div>
      </div>
    </aside>
  )
}
