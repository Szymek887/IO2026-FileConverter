import { useRef, useState } from 'react';
import type { DragEvent } from 'react';
import type { FormatsConfig } from '../types/api';
import { formatFileSize, getAcceptAttribute } from '../utils/files';
import { Icon } from './Icon';

interface FileDropzoneProps {
  config: FormatsConfig;
  selectedCount: number;
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

export function FileDropzone({ config, selectedCount, onFiles, disabled = false }: FileDropzoneProps) {
  const input = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const full = selectedCount >= config.max_files_per_job;
  const locked = disabled || full;

  function dragEnter(event: DragEvent<HTMLDivElement>) {
    if (!event.dataTransfer.types.includes('Files')) return;
    event.preventDefault();
    depth.current += 1;
    if (!locked) setDragging(true);
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    depth.current = 0;
    setDragging(false);
    if (!locked) onFiles(Array.from(event.dataTransfer.files));
  }

  return <div className={`dropzone ${dragging ? 'is-dragging' : ''} ${locked ? 'is-disabled' : ''}`}
    onDragEnter={dragEnter}
    onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = locked ? 'none' : 'copy'; }}
    onDragLeave={event => { event.preventDefault(); depth.current = Math.max(0, depth.current - 1); if (!depth.current) setDragging(false); }}
    onDrop={drop}>
    <input ref={input} type="file" multiple accept={getAcceptAttribute(config)} aria-label="Wybierz pliki" hidden disabled={locked}
      onChange={event => { onFiles(Array.from(event.target.files ?? [])); event.target.value = ''; }} />
    <button type="button" className="dropzone-target" disabled={locked} onClick={() => input.current?.click()}>
      <span className="upload-symbol"><Icon name={full ? 'check' : 'upload'} /></span>
      <strong>{full ? 'Komplet plików!' : dragging ? 'Upuść tutaj!' : 'Przeciągnij i upuść pliki'}</strong>
      <span>{full ? 'Usuń plik z listy, aby wybrać inny.' : `Maks. ${config.max_files_per_job} pliki · do ${formatFileSize(config.max_file_size)} każdy`}</span>
    </button>
    {!full && <div className="import-row"><span>lub</span><button className="button button-orange import-button" type="button" disabled={locked} onClick={() => input.current?.click()}><Icon name="upload" /> Importuj z dysku</button></div>}
  </div>;
}
