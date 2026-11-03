import type { FormatsConfig } from '../types/api';
import { fileKey, formatFileSize, getExtension } from '../utils/files';
import { Icon } from './Icon';

export function FileList({ files, config, onRemove, disabled = false }: { files: readonly File[]; config: FormatsConfig; onRemove: (key: string) => void; disabled?: boolean }) {
  if (!files.length) return null;
  return <section className="selected-files" aria-label="Wybrane pliki">
    <div className="section-label"><h2>Twoje pliki</h2><span>Dodane do listy</span></div>
    <ul className="file-list">{files.map(file => {
      const extension = getExtension(file.name, config.extension_aliases);
      const category = config.categories.find(category => category.formats.includes(extension));
      return <li className="file-row" key={fileKey(file)}>
        <div className="file-illustration" aria-hidden="true"><Icon name="file" /><span>{extension.toUpperCase()}</span></div>
        <div className="file-description"><strong title={file.name}>{file.name}</strong><span>{category?.label} · {formatFileSize(file.size)}</span></div>
        <button className="remove-file" type="button" disabled={disabled} aria-label={`Usuń plik ${file.name}`} onClick={() => onRemove(fileKey(file))}><Icon name="close" /></button>
      </li>;
    })}</ul>
  </section>;
}
