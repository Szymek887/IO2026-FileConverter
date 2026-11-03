import { Icon } from './Icon';

export function ErrorNotice({ messages }: { messages: string[] }) {
  if (!messages.length) return null;
  return <div className="error-notice" role="alert">
    <Icon name="warning" />
    <div>{messages.map((message, index) => <p key={`${index}:${message}`}>{message}</p>)}</div>
  </div>;
}

export function Loading({ label = 'Chwileczkę…' }: { label?: string }) {
  return <div className="loading-state" role="status"><span className="spinner" aria-hidden="true" /><p>{label}</p></div>;
}
