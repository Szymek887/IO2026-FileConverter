import { useState } from 'react';
import { useFormats } from '../hooks/useFormats';
import { useSelectedFiles } from '../hooks/useSelectedFiles';
import type { FormatsConfig } from '../types/api';
import { MascotCard } from '../components/MascotCard';
import { ErrorNotice, Loading } from '../components/Feedback';
import { FileDropzone } from '../components/FileDropzone';
import { FileList } from '../components/FileList';
import { ConversionPanel } from '../features/conversion/ConversionPanel';

export function HomePage() {
  const { config, error, retry } = useFormats();
  return <main id="main-content" className="home-main">
    <div className="page-heading"><span className="eyebrow">AUDIO · WIDEO · OBRAZY</span><h1>Co dziś konwertujemy?</h1></div>
    {!config ? <MascotCard speech="Już się szykuję!" className="converter-mascot">
      {error ? <><ErrorNotice messages={[error]} /><button className="button button-primary" type="button" onClick={retry}>Spróbuj ponownie</button></> : <Loading label="Sprawdzanie dostępnych formatów…" />}
    </MascotCard> : <ConverterWorkspace config={config} />}
  </main>;
}

function ConverterWorkspace({ config }: { config: FormatsConfig }) {
  const { files, errors, addFiles, removeFile, clearFiles } = useSelectedFiles(config);
  const [busy, setBusy] = useState(false);
  return <>
    <MascotCard speech={files.length ? 'Dobry wybór!' : 'Dawaj pliki!'} className="converter-mascot">
      <div className="file-counter" aria-label={`${files.length} z ${config.max_files_per_job} plików`}>
        <span className="counter-dots" aria-hidden="true">{Array.from({ length: config.max_files_per_job }, (_, index) => <i className={index < files.length ? 'filled' : ''} key={index} />)}</span>
        <strong>{files.length} / {config.max_files_per_job} pliki</strong>
      </div>
      <ErrorNotice messages={errors} />
      <FileList files={files} config={config} onRemove={removeFile} disabled={busy} />
      <FileDropzone config={config} selectedCount={files.length} onFiles={addFiles} disabled={busy} />
      <ConversionPanel files={files} formats={config} onReset={clearFiles} onBusyChange={setBusy} />
    </MascotCard>
    <section className="supported-formats" aria-label="Obsługiwane formaty">{config.categories.map(category => <div key={category.id}><h2>{category.label}</h2><p>{category.formats.map(format => format.toUpperCase()).join(' · ')}</p></div>)}</section>
    <p className="page-footnote">Pliki pozostają na Twoim urządzeniu do rozpoczęcia konwersji.</p>
  </>;
}
