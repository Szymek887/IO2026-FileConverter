/** Runtime knobs. Mutable so tests can speed things up. */
export const config = {
  /** Job status polling interval – the contract asks for 1–2 s. */
  pollIntervalMs: 1500,
  /** Timeout of JSON API calls (not uploads/downloads). */
  requestTimeoutMs: 20_000,
}
