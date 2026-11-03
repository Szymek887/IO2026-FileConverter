import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'

export type ArmPose = 'down' | 'raised' | 'wave' | 'cheer' | 'none'
export type Face = 'smile' | 'focus' | 'joy' | 'sad' | 'surprised'
export type Mood = 'idle' | 'busy' | 'cheer' | 'shake'

export interface MascotProps {
  /** Body width in px (shrinks on narrow screens). */
  width: number
  minHeight?: number
  face?: Face
  mood?: Mood
  leftArm?: ArmPose
  rightArm?: ArmPose
  /** Something held in the right hand. */
  holding?: 'envelope'
  bubble?: { text: string; side?: 'left' | 'right' }
  /** Changing this value replays the "shake" animation (e.g. after an error). */
  shakeKey?: number | string
  children?: ReactNode
  className?: string
}

/** Konwuś – the card-shaped mascot from docs/frontend-design. */
export function Mascot({
  width,
  minHeight,
  face = 'smile',
  mood = 'idle',
  leftArm = 'down',
  rightArm = 'down',
  holding,
  bubble,
  shakeKey,
  children,
  className = '',
}: MascotProps) {
  const style = { '--mascot-w': `${width}px`, '--mascot-min-h': `${minHeight ?? 0}px` } as CSSProperties
  const bodyRef = useRef<HTMLDivElement>(null)

  // Replay the shake animation whenever shakeKey changes (but not on first render).
  useEffect(() => {
    const body = bodyRef.current
    if (!body || !shakeKey) return
    body.classList.remove('is-shaking')
    void body.offsetWidth // restart CSS animation
    body.classList.add('is-shaking')
  }, [shakeKey])

  return (
    <div className={`mascot mascot--${mood} ${className}`} style={style}>
      {bubble && (
        <SpeechBubble key={bubble.text} side={bubble.side ?? 'right'}>
          {bubble.text}
        </SpeechBubble>
      )}
      <div className="mascot__figure">
        <Arm side="left" pose={leftArm} />
        <Arm side="right" pose={rightArm} holding={holding} />
        <div className="mascot__leg mascot__leg--left" aria-hidden="true" />
        <div className="mascot__leg mascot__leg--right" aria-hidden="true" />
        <div className="mascot__body" ref={bodyRef}>
          <FaceView face={face} />
          <div className="mascot__content">{children}</div>
        </div>
      </div>
    </div>
  )
}

function SpeechBubble({ side, children }: { side: 'left' | 'right'; children: ReactNode }) {
  return (
    <div className={`bubble bubble--${side}`} role="status" aria-live="polite">
      <span className="bubble__text">{children}</span>
      <svg className="bubble__tail" width="44" height="26" viewBox="0 0 44 26" aria-hidden="true">
        <path d="M6 0 L2 24 L32 0 Z" fill="var(--cream)" />
        <path d="M6 1 L2 24 L32 2" fill="none" stroke="var(--orange)" strokeWidth="3" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

const ARM_PATHS: Record<Exclude<ArmPose, 'none'>, { d: string; hand?: [number, number] }> = {
  down: { d: 'M2 14 C 40 30, 52 78, 34 122' },
  raised: { d: 'M2 124 C 46 104, 64 64, 60 18', hand: [60, 18] },
  wave: { d: 'M2 124 C 46 104, 64 64, 60 18', hand: [60, 18] },
  cheer: { d: 'M2 124 C 40 104, 48 64, 42 18', hand: [42, 18] },
}

function Arm({ side, pose, holding }: { side: 'left' | 'right'; pose: ArmPose; holding?: 'envelope' }) {
  if (pose === 'none') return null
  const { d, hand } = ARM_PATHS[pose]
  const up = pose !== 'down'
  return (
    <svg
      className={`arm arm--${side} arm--${pose} ${up ? 'arm--up' : 'arm--hanging'}`}
      width="80"
      height="140"
      viewBox="0 0 80 140"
      aria-hidden="true"
    >
      {/* The left arm is the right one mirrored inside the SVG, so CSS rotations stay simple. */}
      <g transform={side === 'left' ? 'translate(80 0) scale(-1 1)' : undefined}>
        <path d={d} fill="none" stroke="var(--orange)" strokeWidth="21" strokeLinecap="round" />
        <path d={d} fill="none" stroke="var(--brown)" strokeWidth="13" strokeLinecap="round" />
        {hand && <circle cx={hand[0]} cy={hand[1]} r="13" fill="var(--brown)" stroke="var(--orange)" strokeWidth="4" />}
      </g>
      {holding === 'envelope' && hand && (
        <g className="envelope" transform={`translate(${hand[0] - 34} ${hand[1] - 34}) rotate(-14 34 22)`}>
          <rect x="4" y="6" width="62" height="40" rx="5" fill="var(--cream)" stroke="var(--text)" strokeWidth="3" />
          <path d="M6 9 L35 30 L64 9" fill="none" stroke="var(--text)" strokeWidth="3" strokeLinejoin="round" />
          <g className="envelope__badge">
            <circle cx="64" cy="7" r="9" fill="var(--accent)" stroke="var(--cream)" strokeWidth="2" />
            <text x="64" y="11.5" textAnchor="middle" fontSize="12" fontWeight="800" fill="var(--cream)">
              1
            </text>
          </g>
        </g>
      )}
    </svg>
  )
}

/** Eyes follow the pointer; written to the DOM directly so moving the mouse never re-renders. */
function usePupilTracking() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = ref.current
    if (!root) return
    // Mutable per-effect state, kept in an object so no captured variable is reassigned.
    const pointer: { last: PointerEvent | null; frame: number } = { last: null, frame: 0 }
    const update = () => {
      pointer.frame = 0
      const last = pointer.last
      if (!last) return
      for (const eye of root.querySelectorAll<HTMLElement>('.eye')) {
        const rect = eye.getBoundingClientRect()
        const dx = last.clientX - (rect.left + rect.width / 2)
        const dy = last.clientY - (rect.top + rect.height / 2)
        const dist = Math.hypot(dx, dy) || 1
        const reach = Math.min(1, dist / 220)
        eye.style.setProperty('--px', `${((dx / dist) * 6 * reach).toFixed(2)}px`)
        eye.style.setProperty('--py', `${((dy / dist) * 7 * reach).toFixed(2)}px`)
      }
    }
    const onMove = (event: PointerEvent) => {
      pointer.last = event
      if (!pointer.frame) pointer.frame = requestAnimationFrame(update)
    }
    window.addEventListener('pointermove', onMove)
    return () => {
      window.removeEventListener('pointermove', onMove)
      if (pointer.frame) cancelAnimationFrame(pointer.frame)
    }
  }, [])
  return ref
}

function FaceView({ face }: { face: Face }) {
  const ref = usePupilTracking()
  const closedEyes = face === 'joy'
  return (
    <div className={`face face--${face}`} ref={ref} aria-hidden="true">
      <div className="face__eyes">
        {closedEyes ? (
          <>
            <ClosedEye />
            <ClosedEye />
          </>
        ) : (
          <>
            <span className="eye">
              <span className="eye__pupil" />
            </span>
            <span className="eye">
              <span className="eye__pupil" />
            </span>
          </>
        )}
      </div>
      <span className="face__blush face__blush--left" />
      <span className="face__blush face__blush--right" />
      <Mouth face={face} />
    </div>
  )
}

function ClosedEye() {
  return (
    <svg className="eye-closed" width="40" height="18" viewBox="0 0 40 18">
      <path d="M4 15 Q 20 -2, 36 15" fill="none" stroke="var(--text)" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}

function Mouth({ face }: { face: Face }) {
  switch (face) {
    case 'smile':
      return (
        <svg className="mouth" width="40" height="16" viewBox="0 0 40 16">
          <path d="M6 4 Q 20 16, 34 4" fill="none" stroke="var(--text)" strokeWidth="3.5" strokeLinecap="round" />
        </svg>
      )
    case 'joy':
      return (
        <svg className="mouth mouth--joy" width="56" height="28" viewBox="0 0 56 28">
          <path d="M4 4 H52 Q 50 26, 28 26 Q 6 26, 4 4 Z" fill="var(--accent)" stroke="var(--text)" strokeWidth="3.5" strokeLinejoin="round" />
        </svg>
      )
    case 'sad':
      return (
        <svg className="mouth" width="40" height="16" viewBox="0 0 40 16">
          <path d="M6 13 Q 20 1, 34 13" fill="none" stroke="var(--text)" strokeWidth="3.5" strokeLinecap="round" />
        </svg>
      )
    case 'surprised':
      return (
        <svg className="mouth" width="24" height="24" viewBox="0 0 24 24">
          <ellipse cx="12" cy="12" rx="7" ry="9" fill="var(--accent)" stroke="var(--text)" strokeWidth="3" />
        </svg>
      )
    case 'focus':
      return null
  }
}
