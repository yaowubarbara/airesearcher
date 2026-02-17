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
  direction_id?: string;
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
  missing_references?: string[];
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

export interface DownloadedPaper {
  id: string;
  title: string;
  authors: string[];
  year: number;
  doi?: string;
  journal: string;
  status: string;
  pdf_path?: string;
}

export interface WishlistPaper {
  id: string;
  title: string;
  authors: string[];
  year: number;
  doi?: string;
  journal: string;
  recommended?: boolean;
}

export interface WishlistGroup {
  id: string;
  query: string;
  timestamp: number;
  total_found: number;
  downloaded: number;
  needing_pdf: number;
  recommended_count?: number;
  papers: WishlistPaper[];
}

export interface WishlistResponse {
  total_count: number;
  groups: WishlistGroup[];
}

export interface DownloadedGroup {
  id: string;
  query: string;
  timestamp: number;
  paper_count: number;
  papers: DownloadedPaper[];
}

export interface DownloadedResponse {
  total_count: number;
  groups: DownloadedGroup[];
}

export interface SearchSession {
  id: string;
  query: string;
  total_papers: number;
  indexed_count: number;
  created_at: string;
}

export interface SessionPaper {
  id: string;
  title: string;
  authors: string[];
  year: number;
  doi?: string;
  journal: string;
  status: string;
  pdf_path?: string;
  recommended: boolean;
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

export interface ReadinessItem {
  author: string;
  title: string;
  category: 'primary' | 'criticism';
  reason: string;
  available: boolean;
}

export interface ReadinessReport {
  query: string;
  status: 'ready' | 'missing_primary' | 'insufficient_criticism' | 'not_ready';
  items: ReadinessItem[];
  summary: string;
}

export interface TheoryItem {
  author: string;
  title: string;
  relevance: string;
  year?: number;
  source: 'crossref' | 'openalex' | 'llm_only';
  verified: boolean;
  already_in_db: boolean;
  has_full_text: boolean;
}

export interface TheorySupplementResult {
  plan_id: string;
  total_recommended: number;
  verified: number;
  inserted: number;
  already_present: number;
  items: TheoryItem[];
  summary: string;
}

export interface ManualAddResult {
  already_exists: boolean;
  paper_id: string;
  reference_id?: string;
  title: string;
  authors?: string[];
  year?: number;
  journal?: string;
  doi?: string;
}

export interface CrossRefMatch {
  doi: string;
  title: string;
  authors: string[];
  year: number;
  journal: string;
  volume?: string;
  issue?: string;
  pages?: string;
}

export interface SynthesizedTopic {
  title: string;
  research_question: string;
  gap_description: string;
  source_paper_ids?: string[];
}

export interface PlanMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
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

export interface PaperAnnotation {
  id: string;
  paper_id: string;
  tensions: string[];
  mediators: string[];
  scale: string;
  gap: string;
  evidence: string;
  deobjectification: string;
}

export interface ProblematiqueDirection {
  id: string;
  title: string;
  description: string;
  dominant_tensions: string[];
  dominant_mediators: string[];
  dominant_scale?: string;
  dominant_gap?: string;
  paper_ids: string[];
  topic_ids: string[];
  recency_score?: number;
}

export interface DirectionWithTopics {
  direction: ProblematiqueDirection;
  topics: Topic[];
}

export interface AnnotationStatus {
  total_papers: number;
  papers_with_abstract: number;
  annotated: number;
  unannotated: number;
  directions: number;
  topics: number;
}

export interface CorpusStudiedItem {
  author: string;
  works: string[];
  studied_by: string;
}

export interface SmartSearchRef {
  paper_id: string;
  title: string;
  authors: string[];
  year: number;
  doi?: string;
  journal: string;
  category: string;
  tier: number;
  usage_note: string;
  source_phase: string;
}

export interface SmartSearchResult {
  blueprint_suggested: number;
  verified: number;
  hallucinated: number;
  expanded_pool: number;
  final_selected: number;
  categories: Record<string, number>;
  tier_counts: Record<number, number>;
  gaps: string[];
  references: SmartSearchRef[];
}
