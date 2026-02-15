export interface Journal {
  name: string;
  publisher: string;
  language: string;
  citation_style: string;
  scope: string;
  issn: string;
  is_active: boolean;
}

export interface Topic {
  id: string;
  title: string;
  research_question: string;
  gap_description: string;
  target_journals: string[];
  novelty_score: number;
  feasibility_score: number;
  journal_fit_score: number;
  timeliness_score: number;
  overall_score: number;
  status: string;
  created_at?: string;
}

export interface OutlineSection {
  title: string;
  argument: string;
  primary_texts: string[];
  passages_to_analyze: string[];
  secondary_sources: string[];
  estimated_words: number;
}

export interface ResearchPlan {
  id: string;
  topic_id: string;
  thesis_statement: string;
  target_journal: string;
  target_language: string;
  outline: OutlineSection[];
  reference_ids: string[];
  status: string;
  primary_text_report?: PrimaryTextReport;
  created_at?: string;
}

export interface MissingPrimaryText {
  text_name: string;
  sections_needing: string[];
  passages_needed: string[];
  purpose: string;
}

export interface PrimaryTextReport {
  total_unique: number;
  available: string[];
  missing: MissingPrimaryText[];
}

export interface Manuscript {
  id: string;
  plan_id: string;
  title: string;
  target_journal: string;
  language: string;
  sections: Record<string, string>;
  full_text?: string;
  abstract?: string;
  keywords: string[];
  word_count: number;
  version: number;
  status: string;
  review_scores: Record<string, number>;
  created_at?: string;
  updated_at?: string;
}

export interface ReviewResult {
  scores: Record<string, number>;
  comments: string[];
  revision_instructions: string[];
  overall_recommendation: string;
}

export interface WishlistPaper {
  id: string;
  title: string;
  authors: string[];
  year: number;
  doi?: string;
  journal: string;
}

export interface TaskProgress {
  taskId: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  message: string;
  result?: any;
  error?: string;
}

export interface AcquisitionReport {
  query: string;
  found: number;
  downloaded: number;
  indexed: number;
  oa_resolved: number;
  summary: string;
}

export interface StatsData {
  papers_indexed: number;
  topics_discovered: number;
  llm_usage: {
    total_cost_usd?: number;
    total_tokens?: number;
    by_model?: Record<string, { tokens: number; cost: number }>;
    by_task?: Record<string, { tokens: number; cost: number }>;
  };
}
