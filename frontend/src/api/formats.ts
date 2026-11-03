import { ApiError, apiRequest } from './client';
import type { FormatsConfig } from '../types/api';

export async function getFormats(signal?: AbortSignal): Promise<FormatsConfig> {
  const config = await apiRequest<FormatsConfig>('/formats', { signal });
  const valid = config && Number.isSafeInteger(config.max_file_size) && config.max_file_size > 0
    && Number.isSafeInteger(config.max_files_per_job) && config.max_files_per_job > 0
    && Array.isArray(config.categories) && config.categories.length > 0
    && config.categories.every(category => typeof category.id === 'string' && typeof category.label === 'string'
      && Array.isArray(category.formats) && category.formats.every(format => typeof format === 'string'))
    && config.conversions && typeof config.conversions === 'object'
    && Object.values(config.conversions).every(targets => Array.isArray(targets) && targets.every(target => typeof target === 'string'))
    && config.extension_aliases && typeof config.extension_aliases === 'object'
    && Object.values(config.extension_aliases).every(alias => typeof alias === 'string');
  if (!valid) throw new ApiError(200, 'INVALID_RESPONSE', 'Nie udało się odczytać obsługiwanych formatów. Spróbuj ponownie.');
  return config;
}
