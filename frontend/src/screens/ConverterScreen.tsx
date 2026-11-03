import { useCallback, useEffect, useState } from 'react'
import { ApiError, getFormats } from '../api/client'
import type { FormatsResponse } from '../api/types'
import type { SelectedFile } from '../lib/files'
import { useConversion } from '../lib/useConversion'
import { HomeStage } from './HomeStage'
import { PickStage } from './PickStage'
import { ResultStage } from './ResultStage'

type Stage = 'home' | 'pick' | 'result'

interface ConverterScreenProps {
  onUnauthenticated: (message: string) => void
}

export function ConverterScreen({ onUnauthenticated }: ConverterScreenProps) {
  const [stage, setStage] = useState<Stage>('home')
  const [formats, setFormats] = useState<FormatsResponse | null>(null)
  const [formatsError, setFormatsError] = useState<string | null>(null)
  const [files, setFiles] = useState<SelectedFile[]>([])
  const conversion = useConversion(onUnauthenticated)

  const loadFormats = useCallback(async () => {
    setFormatsError(null)
    try {
      setFormats(await getFormats())
    } catch (e) {
      if (e instanceof ApiError && e.code === 'UNAUTHENTICATED') return onUnauthenticated(e.message)
      setFormatsError(e instanceof ApiError ? e.message : 'Nie udało się pobrać listy formatów.')
    }
  }, [onUnauthenticated])

  useEffect(() => {
    void loadFormats()
  }, [loadFormats])

  const convert = () => {
    conversion.start(files)
    setStage('result')
  }

  const again = () => {
    conversion.reset()
    setFiles([])
    setStage('pick')
  }

  return (
    <div className="stage" key={stage}>
      {stage === 'home' && (
        <HomeStage onStart={() => setStage('pick')} loading={!formats} error={formatsError} onRetry={loadFormats} />
      )}
      {stage === 'pick' && formats && (
        <PickStage formats={formats} files={files} onFilesChange={setFiles} onConvert={convert} />
      )}
      {stage === 'result' && (
        <ResultStage
          items={conversion.items}
          finished={conversion.finished}
          onAgain={again}
          onUnauthenticated={onUnauthenticated}
        />
      )}
    </div>
  )
}
