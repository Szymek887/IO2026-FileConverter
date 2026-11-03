import { useReducer } from 'react';
import type { FormatsConfig } from '../types/api';
import { fileKey, getCommonTargets, validateFileSelection } from '../utils/files';

export function useSelectedFiles(config: FormatsConfig) {
  type State = { files: File[]; errors: string[] };
  type Action = { type: 'add'; files: readonly File[] } | { type: 'remove'; key: string } | { type: 'clear' };
  const [{ files, errors }, dispatch] = useReducer((state: State, action: Action): State => {
    if (action.type === 'clear') return { files: [], errors: [] };
    if (action.type === 'remove') return { files: state.files.filter(file => fileKey(file) !== action.key), errors: [] };
    if (!action.files.length) return state;
    const result = validateFileSelection(state.files, action.files, config);
    return result.ok ? { files: result.files, errors: [] } : { ...state, errors: result.errors };
  }, { files: [], errors: [] });

  function addFiles(incoming: readonly File[]) {
    dispatch({ type: 'add', files: incoming });
  }

  function removeFile(key: string) {
    dispatch({ type: 'remove', key });
  }

  function clearFiles() { dispatch({ type: 'clear' }); }

  return { files, errors, addFiles, removeFile, clearFiles, commonTargets: getCommonTargets(files, config) };
}
