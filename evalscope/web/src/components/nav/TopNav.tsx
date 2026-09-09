import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useLocale } from '@/contexts/LocaleContext'
import ThemeToggle from './ThemeToggle'
import { BarChart3, Gauge, FlaskConical, BookOpen, FileText, Menu, X } from 'lucide-react'

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `coarse-target flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
    isActive
      ? 'bg-[var(--accent)] text-[var(--text-on-filled)] shadow-[var(--shadow-glow-soft)]'
      : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-card2)]'
  }`

const iconLinkClass = ({ isActive }: { isActive: boolean }) =>
  `coarse-target flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-200 ${
    isActive
      ? 'bg-[var(--accent)] text-[var(--text-on-filled)] shadow-[var(--shadow-glow-soft)]'
      : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-card2)]'
  }`

const mobileLinkClass = ({ isActive }: { isActive: boolean }) =>
  `coarse-target flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
    isActive
      ? 'bg-[var(--accent)] text-white'
      : 'text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-card2)]'
  }`

export default function TopNav() {
  const { t } = useLocale()
  const [mobileOpen, setMobileOpen] = useState(false)

  const navItems = [
    { to: '/dashboard', icon: <BarChart3 size={15} />, label: t('nav.dashboard') },
    { to: '/reports', icon: <FileText size={15} />, label: t('nav.evaluations') },
    { to: '/performance', icon: <Gauge size={15} />, label: t('nav.performance') },
    { to: '/tasks', icon: <FlaskConical size={15} />, label: t('nav.tasks') },
    { to: '/benchmarks', icon: <BookOpen size={15} />, label: t('nav.benchmarks') },
  ]

  return (
    <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--surface-glass)] backdrop-blur-xl">
      {/* Subtle gradient line at top */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[var(--accent)] to-transparent opacity-40" />
      <div className="flex items-center justify-between px-4 max-w-[1600px] mx-auto" style={{ height: '52px' }}>
        {/* Brand */}
        <div className="flex items-center gap-3 lg:gap-5 min-w-0">
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-8 h-8 flex items-center justify-center">
              <img src="/bharatgen-icon-180.png" alt="BharatGen" width={32} height={32} className="rounded-full" />
            </div>
          </div>
          {/* Desktop nav — full text, lg+ */}
          <nav className="hidden lg:flex items-center gap-0.5">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={linkClass}>
                {item.icon} {item.label}
              </NavLink>
            ))}
          </nav>
          {/* Tablet nav — icon only, md to lg */}
          <nav className="hidden md:flex lg:hidden items-center gap-0.5">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={iconLinkClass} title={item.label}>
                {item.icon}
              </NavLink>
            ))}
          </nav>
        </div>
        {/* Right */}
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <ThemeToggle />
          {/* Mobile menu button */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="coarse-target md:hidden w-8 h-8 flex items-center justify-center rounded-lg text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--bg-card2)] transition-all duration-200"
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>
      {/* Mobile nav dropdown — animated */}
      <div
        className={`md:hidden overflow-hidden transition-[max-height,opacity] duration-300 ease-in-out ${
          mobileOpen ? 'max-h-80 opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <nav className="border-t border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 flex flex-col gap-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={mobileLinkClass}
              onClick={() => setMobileOpen(false)}
            >
              {item.icon} {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
