import { useMemo, type CSSProperties } from 'react'

/** CD logo + "KONWUŚ" wordmark (top-left on every screen). */
export function Logo() {
  return (
    <div className="logo" aria-label="Konwuś">
      <svg className="logo__cd" width="52" height="52" viewBox="0 0 52 52" aria-hidden="true">
        <defs>
          <linearGradient id="cd-sheen" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#d9d4f0" />
            <stop offset="0.25" stopColor="#a8d8c8" />
            <stop offset="0.45" stopColor="#f2f2f2" />
            <stop offset="0.6" stopColor="#f3e3a1" />
            <stop offset="0.8" stopColor="#c6c2e8" />
            <stop offset="1" stopColor="#9ec1e0" />
          </linearGradient>
        </defs>
        <circle cx="26" cy="26" r="24" fill="url(#cd-sheen)" stroke="#1d1d1d" strokeWidth="2" />
        <circle cx="26" cy="26" r="9" fill="#f4f4f4" stroke="#7a7a7a" strokeWidth="1.5" />
        <circle cx="26" cy="26" r="4" fill="var(--bg)" stroke="#1d1d1d" strokeWidth="1.5" />
        <path d="M12 16 A 17 17 0 0 1 22 10" stroke="#fff" strokeWidth="2.5" fill="none" strokeLinecap="round" opacity="0.8" />
      </svg>
      <span className="logo__text">KONWUŚ</span>
    </div>
  )
}

export function AvatarIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8.5" r="4.5" fill="var(--pink)" />
      <path d="M3.5 21 C 4.5 15.5, 19.5 15.5, 20.5 21 Z" fill="var(--pink)" />
    </svg>
  )
}

export function UploadIcon() {
  return (
    <svg className="upload-icon" width="64" height="56" viewBox="0 0 64 56" aria-hidden="true">
      <path d="M6 30 V50 H58 V30" fill="none" stroke="var(--pink)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <path className="upload-icon__arrow" d="M32 38 V6 M18 19 L32 5 L46 19" fill="none" stroke="var(--pink)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function DownloadIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <path d="M13 3 V17 M6 11 L13 18 L20 11 M5 23 H21" fill="none" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Document icon with a coloured format label (source = accent, output = teal). */
export function FileIcon({ label, variant }: { label: string; variant: 'source' | 'target' }) {
  return (
    <svg className="file-icon" width="50" height="58" viewBox="0 0 50 58" aria-hidden="true">
      <path d="M8 2 H31 L44 15 V55 H8 Z" fill="var(--cream)" stroke="var(--text)" strokeWidth="2.5" strokeLinejoin="round" />
      <path d="M31 2 V15 H44" fill="none" stroke="var(--text)" strokeWidth="2.5" strokeLinejoin="round" />
      <rect x="1" y="31" width="40" height="14" rx="3" fill={variant === 'source' ? 'var(--accent)' : 'var(--teal)'} />
      <text x="21" y="41.5" textAnchor="middle" fontSize="9" fontWeight="800" fill="var(--cream)">
        {label.toUpperCase()}
      </text>
    </svg>
  )
}

const CONFETTI_COLORS = ['var(--orange)', 'var(--teal)', 'var(--accent)', 'var(--brown)']

/** Falling confetti pieces around the "Gotowe!" mascot. */
export function Confetti({ count = 26 }: { count?: number }) {
  const pieces = useMemo(
    () =>
      Array.from({ length: count }, (_, i) => ({
        left: (i * 37 + 11) % 100,
        delay: ((i * 0.37) % 2.4).toFixed(2),
        duration: (3.2 + ((i * 0.53) % 2.2)).toFixed(2),
        rotate: (i * 47) % 360,
        drift: ((i % 5) - 2) * 18,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      })),
    [count],
  )
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => (
        <span
          key={i}
          className="confetti__piece"
          style={
            {
              left: `${p.left}%`,
              background: p.color,
              animationDelay: `${p.delay}s`,
              animationDuration: `${p.duration}s`,
              '--rot': `${p.rotate}deg`,
              '--drift': `${p.drift}px`,
            } as CSSProperties
          }
        />
      ))}
    </div>
  )
}
