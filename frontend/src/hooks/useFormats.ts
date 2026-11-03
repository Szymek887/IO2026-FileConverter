import { useEffect, useState } from 'react';
import { getFormats } from '../api/formats';
import { errorMessage, isAbortError } from '../api/client';
import type { FormatsConfig } from '../types/api';

export function useFormats() {
  const [config, setConfig] = useState<FormatsConfig | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError('');
    void getFormats(controller.signal).then(data => {
      if (!controller.signal.aborted) setConfig(data);
    }).catch(error => {
      if (!controller.signal.aborted && !isAbortError(error)) setError(errorMessage(error));
    });
    return () => controller.abort();
  }, [attempt]);
  return { config, error, retry: () => setAttempt(value => value + 1) };
}
