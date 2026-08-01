import type { Metadata, Viewport } from 'next'
import { Noto_Serif_SC, Rokkitt } from 'next/font/google'
import './globals.css'

const _notoSerifSC = Noto_Serif_SC({
  weight: ['400', '500', '600', '700'],
  subsets: ['latin'],
  variable: '--font-noto-serif-sc',
  display: 'swap',
  preload: false,
})

const _rokkitt = Rokkitt({
  subsets: ['latin'],
  variable: '--font-rokkitt',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'AI 助手控制台',
  description: '个人 AI 助手管理界面 — 对话、待办、笔记、提醒一体化',
}

export const viewport: Viewport = {
  colorScheme: 'light',
  themeColor: '#fbfbfa',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-CN" className="bg-background">
      <body className={`${_notoSerifSC.variable} ${_rokkitt.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  )
}
