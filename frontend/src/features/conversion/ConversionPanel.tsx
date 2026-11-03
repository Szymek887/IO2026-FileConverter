import type { FormatsConfig } from '../../types/api';
import { Icon } from '../../components/Icon';

/** Uzgodniony punkt integracji osoby B. Pliki to oryginalne obiekty File. */
export interface ConversionPanelProps {
  files: readonly File[];
  formats: FormatsConfig;
  onReset: () => void;
  /** Osoba B ustawia true na czas wysyłania/konwersji, żeby zablokować zmianę plików. */
  onBusyChange: (busy: boolean) => void;
}

/** Tu osoba B dodaje picker, POST /jobs, polling i pobieranie. Bez pozorowanej konwersji. */
export function ConversionPanel({ files }: ConversionPanelProps) {
  if (!files.length) return null;
  return <p className="ready-note" role="status"><Icon name="check" />{files.length === 1 ? 'Plik dodany do konwersji' : 'Pliki dodane do konwersji'}</p>;
}
