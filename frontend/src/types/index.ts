export interface User {
  id: number;
  username: string;
  email?: string | null;
  role: 'admin' | 'architect' | 'viewer';
  created_at?: string;
  last_login?: string | null;
}

export interface AuthResponse {
  message?: string;
  token: string;
  access_token: string;
  refresh_token: string;
  user: User;
}

export interface Project {
  id: number;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
  documents?: Document[];
  document_count?: number;
}

export interface Document {
  id: number;
  project_id: number;
  filename: string;
  original_filename: string;
  file_size?: number;
  status: string;
  upload_date?: string;
  ai_model?: string;
  analysis_status?: string;
  metadata?: Record<string, any>;
}

export interface ControlSchedule {
  id: number;
  project_id: number;
  document_id?: number | null;
  name: string;
  hostname: string;
  schedule_type: 'once' | 'hourly' | 'daily' | 'weekly' | 'monthly';
  day_of_week?: number | null;
  day_of_month?: string | null;
  run_time?: string | null;
  interval_minutes?: number | null;
  is_active: boolean;
  status?: string;
  last_run_at?: string | null;
  next_run_at?: string | null;
  created_at?: string;
}

export interface ControlRunHistory {
  id: number;
  schedule_id: number;
  project_id: number;
  status: 'SUCCESS' | 'FAILED' | 'RUNNING';
  started_at: string;
  finished_at?: string | null;
  log_output?: string;
  error_message?: string | null;
}

export interface TargetArtifact {
  id: number;
  project_id: number;
  document_id: number;
  artifact_type: string;
  name: string;
  content: string;
  created_at?: string;
}
