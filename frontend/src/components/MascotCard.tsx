import type { ReactNode } from 'react';

export function MascotCard({ children, speech, className = '' }: { children: ReactNode; speech: string; className?: string }) {
  return <div className={`mascot-wrap ${className}`}>
    <p className="speech-bubble" aria-hidden="true">{speech}</p>
    <svg className="mascot-arm mascot-arm-left" viewBox="0 0 70 150" aria-hidden="true"><path d="M60 12Q-4 60 24 127" /></svg>
    <svg className="mascot-arm mascot-arm-right" viewBox="0 0 70 150" aria-hidden="true"><path d="M60 12Q-4 60 24 127" /></svg>
    <div className="mascot-body">
      <div className="mascot-face" aria-hidden="true">
        <span className="eye"><i /></span><span className="eye"><i /></span>
        <span className="cheek cheek-left" /><span className="cheek cheek-right" />
      </div>
      {children}
    </div>
    <span className="mascot-foot foot-left" aria-hidden="true" />
    <span className="mascot-foot foot-right" aria-hidden="true" />
  </div>;
}
