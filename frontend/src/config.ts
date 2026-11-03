/** Demo jest dostępne wyłącznie w serwerze developerskim, nigdy w buildzie produkcyjnym. */
export const isDemo = import.meta.env.DEV && import.meta.env.MODE === 'demo';
export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
