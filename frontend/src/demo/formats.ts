import type { FormatsConfig } from '../types/api';

/** Przykład z dostarczonego api-contract.md; używany wyłącznie w demonstracji i testach. */
export const demoFormats: FormatsConfig = {
  max_file_size: 262_144_000,
  max_files_per_job: 2,
  categories: [
    { id: 'audio', label: 'Audio', formats: ['flac', 'mp3', 'wav'] },
    { id: 'video', label: 'Wideo', formats: ['gif', 'mp4', 'mov'] },
    { id: 'image', label: 'Obraz', formats: ['jpg', 'png', 'heic'] },
  ],
  conversions: {
    flac: ['mp3', 'wav'], mp3: ['flac', 'wav'], wav: ['flac', 'mp3'],
    gif: ['mp4', 'mov'], mp4: ['gif', 'mov'], mov: ['gif', 'mp4'],
    jpg: ['png', 'heic'], png: ['jpg', 'heic'], heic: ['jpg', 'png'],
  },
  extension_aliases: { jpeg: 'jpg', heif: 'heic' },
};
