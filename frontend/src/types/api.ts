export interface ApiErrorBody {
  status: 'error';
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface AuthSession {
  email: string;
  /** Unix time, w sekundach — tak jak w kontrakcie. */
  session_expires: number;
}

export interface OtpResponse {
  status: 'ok';
  message: string;
  otp_expires: number;
  resend_available_in: number;
}

export interface FormatCategory {
  id: string;
  label: string;
  formats: string[];
}

export interface FormatsConfig {
  max_file_size: number;
  max_files_per_job: number;
  categories: FormatCategory[];
  conversions: Record<string, string[]>;
  extension_aliases: Record<string, string>;
}
