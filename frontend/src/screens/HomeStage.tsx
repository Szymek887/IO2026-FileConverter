import { Mascot } from '../components/Mascot'

interface HomeStageProps {
  onStart: () => void
  loading: boolean
  error: string | null
  onRetry: () => void
}

export function HomeStage({ onStart, loading, error, onRetry }: HomeStageProps) {
  return (
    <section className="screen screen--home" aria-label="Start">
      <Mascot
        width={340}
        minHeight={380}
        face={error ? 'sad' : 'smile'}
        leftArm="down"
        rightArm="down"
        bubble={{ text: error ? 'Coś mi nie działa… 😵' : 'Co dziś konwertujemy?', side: 'right' }}
        className="screen__mascot"
      >
        <div className="home">
          {error ? (
            <>
              <p className="form__error" role="alert">
                {error}
              </p>
              <button type="button" className="btn btn--cta" onClick={onRetry}>
                Spróbuj ponownie
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn btn--big" onClick={onStart} disabled={loading}>
                KONWERTUJ
              </button>
              <p className="home__sub">wideo · audio · obrazy</p>
            </>
          )}
        </div>
      </Mascot>
    </section>
  )
}
