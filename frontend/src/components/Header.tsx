import { AvatarIcon, Logo } from './Icons'

interface HeaderProps {
  email?: string
  onLogout?: () => void
}

export function Header({ email, onLogout }: HeaderProps) {
  return (
    <header className="header">
      <Logo />
      {email && onLogout && (
        <div className="header__user">
          <button type="button" className="link-button header__logout" onClick={onLogout}>
            Wyloguj
          </button>
          <span className="avatar" title={email} aria-label={`Zalogowano jako ${email}`} role="img">
            <AvatarIcon />
          </span>
        </div>
      )}
    </header>
  )
}
