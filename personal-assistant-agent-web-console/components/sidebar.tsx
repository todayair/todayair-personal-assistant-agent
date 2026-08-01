'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  MessageSquare,
  CheckSquare,
  FileText,
  Bell,
  Clock,
  Activity,
  Bot,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/chat', label: '对话', icon: MessageSquare, description: 'AI 聊天' },
  { href: '/todos', label: '待办', icon: CheckSquare, description: '任务管理' },
  { href: '/notes', label: '笔记', icon: FileText, description: '知识记录' },
  { href: '/reminders', label: '提醒', icon: Bell, description: '定时提醒' },
  { href: '/history', label: '历史', icon: Clock, description: '会话记录' },
  { href: '/status', label: '状态', icon: Activity, description: '系统概览' },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="flex h-full w-56 flex-col bg-sidebar text-sidebar-foreground">
      {/* Logo / Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-sidebar-border px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
          <Bot className="h-4 w-4 text-primary-foreground" />
        </div>
        <div className="flex flex-1 items-center justify-center leading-none">
          <span className="font-rokkitt text-lg font-semibold text-sidebar-accent-foreground">
            todayair's agent
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3" aria-label="主导航">
        <ul className="space-y-0.5 px-2">
          {navItems.map(({ href, label, icon: Icon, description }) => {
            const isActive = pathname === href || pathname.startsWith(href + '/')
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={cn(
                    'group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-all duration-150',
                    isActive
                      ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                      : 'text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground',
                  )}
                  aria-current={isActive ? 'page' : undefined}
                >
                  <Icon
                    className={cn(
                      'h-4 w-4 shrink-0 transition-colors',
                      isActive ? 'text-primary' : 'text-sidebar-foreground/60 group-hover:text-sidebar-foreground',
                    )}
                  />
                  <span className="flex-1">{label}</span>
                  {isActive && (
                    <ChevronRight className="h-3 w-3 text-sidebar-foreground/40" />
                  )}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
          <span className="text-[11px] text-sidebar-foreground/50">在线 · v1.0</span>
        </div>
      </div>
    </aside>
  )
}
