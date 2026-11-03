import type { ReactNode } from 'react';

const paths: Record<string, ReactNode> = {
  upload: <><path d="M12 16V3m-5 5 5-5 5 5" /><path d="M4 14v6h16v-6" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  file: <><path d="M14 2H5v20h14V7z" /><path d="M14 2v6h5M8 13h8M8 17h6" /></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 6 9 7 9-7" /></>,
  key: <><circle cx="8" cy="9" r="5" /><path d="m12 13 8 8m-4-4 3-3m-7-1 3-3" /></>,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 22v-3a8 8 0 0 1 16 0v3" /></>,
  logout: <><path d="M10 4H4v16h6m3-4 4-4-4-4m-5 4h13" /></>,
  shield: <><path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6z" /><path d="m8 12 3 3 5-6" /></>,
  warning: <><path d="M12 3 2 21h20zM12 9v5" /><path d="M12 17h.01" /></>,
};

export function Icon({ name, className = '' }: { name: keyof typeof paths; className?: string }) {
  return <svg className={`icon ${className}`} width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {paths[name]}
  </svg>;
}
