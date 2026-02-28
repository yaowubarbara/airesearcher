export interface Journal {
  name: string;
  publisher: string;
  language: string;
  citation_style: string;
  scope: string;
  issn: string;
  is_active: boolean;
}

export interface Domain {
  domain_id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  journal_count: number;
}

export interface Direction {
  id: string;
  title: string;
  description: string;
  dominant_tensions: string[];
  paper_ids: string[];
  recency_score: number;
  topic_ids: string[];
}

export interface Topic {
  id: string;
  title: string;
  thesis_seed: string;
  direction_id: string;
  novelty: string;
  feasibility: string;
  status: string;
  target_journals: string[];
}

export interface TaskStatus {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  message: string;
  result?: unknown;
}
