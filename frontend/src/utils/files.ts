import type { FormatsConfig } from '../types/api';

export function getExtension(name: string, aliases: Record<string, string> = {}): string {
  const dot = name.lastIndexOf('.');
  const extension = dot > 0 ? name.slice(dot + 1).toLowerCase() : '';
  return Object.hasOwn(aliases, extension) ? aliases[extension] : extension;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const unit = bytes < 1024 ** 2 ? 'KiB' : bytes < 1024 ** 3 ? 'MiB' : 'GiB';
  const divisor = unit === 'KiB' ? 1024 : unit === 'MiB' ? 1024 ** 2 : 1024 ** 3;
  return `${new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 }).format(bytes / divisor)} ${unit}`;
}

export function fileKey(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

export function getCommonTargets(files: readonly File[], config: FormatsConfig): string[] {
  if (!files.length) return [];
  const lists = files.map(file => config.conversions[getExtension(file.name, config.extension_aliases)] ?? []);
  return [...new Set(lists[0])].filter(target => lists.every(list => list.includes(target)));
}

export function getAcceptAttribute(config: FormatsConfig): string {
  const extensions = config.categories.flatMap(category => category.formats);
  return [...new Set([...extensions, ...Object.keys(config.extension_aliases)])].map(ext => `.${ext}`).join(',');
}

export type FileValidationResult =
  | { ok: true; files: File[]; commonTargets: string[] }
  | { ok: false; errors: string[] };

/** Dodanie jest atomowe: odrzucony wybór nie usuwa wcześniej wybranych plików. */
export function validateFileSelection(current: readonly File[], incoming: readonly File[], config: FormatsConfig): FileValidationResult {
  const files = [...current, ...incoming];
  if (files.length > config.max_files_per_job) {
    return { ok: false, errors: [`Możesz wybrać maksymalnie ${config.max_files_per_job} pliki naraz. Usuń plik z listy, aby dodać inny.`] };
  }
  const allowed = new Set(config.categories.flatMap(category => category.formats));
  const seen = new Set<string>();
  const errors: string[] = [];
  for (const file of files) {
    if (seen.has(fileKey(file))) errors.push(`Plik „${file.name}” jest już na liście.`);
    seen.add(fileKey(file));
    if (file.size > config.max_file_size) errors.push(`Plik „${file.name}” przekracza limit ${formatFileSize(config.max_file_size)}.`);
    const extension = getExtension(file.name, config.extension_aliases);
    if (!allowed.has(extension)) errors.push(`Format pliku „${file.name}” nie jest obsługiwany.`);
  }
  if (errors.length) return { ok: false, errors };
  const commonTargets = getCommonTargets(files, config);
  if (files.length && !commonTargets.length) {
    return { ok: false, errors: ['Te pliki nie mają wspólnego formatu docelowego. Wybierz zgodne pliki lub konwertuj je osobno.'] };
  }
  return { ok: true, files, commonTargets };
}
