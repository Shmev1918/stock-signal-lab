import type { ReactNode } from 'react'

type Props = {
  title: string
  subtitle?: string
  children: ReactNode
}

export default function Layout({ title, subtitle, children }: Props) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">Local cockpit</div>
          <h1>{title}</h1>
          {subtitle ? <p className="muted">{subtitle}</p> : null}
        </div>
      </header>
      <main className="content">{children}</main>
    </div>
  )
}
