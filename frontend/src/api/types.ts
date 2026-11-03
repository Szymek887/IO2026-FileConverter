// Shapes from docs/api-contract.md (v1.0). Keep in sync with docs/openapi.yaml.

export type Format = 'flac' | 'mp3' | 'wav' | 'gif' | 'mp4' | 'mov' | 'jpg' | 'png' | 'heic'
export type Category = 'audio' | 'video' | 'image'

export interface ApiErrorBody {
  status: 'error'
  code: string
  message: string
  details?: Record<string, unknown> | null
}

export interface RequestOtpResponse {
  status: 'ok'
  message: string
  otp_expires: number
  resend_available_in: number
}

export interface SessionInfo {
  email: string
  session_expires: number
}

export interface CategoryInfo {
  id: Category
  label: string
  formats: Format[]
}

export interface FormatsResponse {
  max_file_size: number
  max_files_per_job: number
  categories: CategoryInfo[]
  conversions: Record<Format, Format[]>
  extension_aliases: Record<string, Format>
}

export interface InputFileInfo {
  id: string
  name: string
  extension: Format
  category: Category
  size: number
}

export interface OutputFileInfo {
  index: number
  name: string
  size: number
  url: string
}

export interface ResultInfo {
  finished_at: number
  status: 'success' | 'error'
  message: string
  output_files: OutputFileInfo[]
  expires_at: number | null
}

export type JobStatus = 'queued' | 'processing' | 'done' | 'error'

export interface Job {
  id: string
  created_at: number
  target_format: Format
  status: JobStatus
  files: InputFileInfo[]
  result: ResultInfo | null
}
