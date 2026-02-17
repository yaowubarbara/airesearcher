'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import type { CrossRefMatch } from '@/lib/types';

interface Props {
  prefillTitle?: string;
  prefillAuthors?: string;
  compact?: boolean;
  defaultRefType?: string;
  sessionId?: string;
  onAdded?: (result: any) => void;
}

const REF_TYPES = [
  { value: '', label: 'Unclassified' },
  { value: 'primary_literary', label: 'Primary Literary' },
  { value: 'secondary_criticism', label: 'Secondary Criticism' },
  { value: 'theory', label: 'Theory' },
  { value: 'methodology', label: 'Methodology' },
  { value: 'historical_context', label: 'Historical Context' },
  { value: 'reference_work', label: 'Reference Work' },
];

export default function ManualAddForm({
  prefillTitle,
  prefillAuthors,
  compact,
  defaultRefType,
  sessionId,
  onAdded,
}: Props) {
  // DOI quick-add state
  const [doiInput, setDoiInput] = useState('');
  const [doiLoading, setDoiLoading] = useState(false);
  const [doiResult, setDoiResult] = useState<string | null>(null);

  // Full form state
  const [showFullForm, setShowFullForm] = useState(false);
  const [title, setTitle] = useState(prefillTitle || '');
  const [authors, setAuthors] = useState(prefillAuthors || '');
  const [year, setYear] = useState('');
  const [journal, setJournal] = useState('');
  const [doi, setDoi] = useState('');
  const [refType, setRefType] = useState(defaultRefType || '');
  const [formLoading, setFormLoading] = useState(false);
  const [formResult, setFormResult] = useState<string | null>(null);

  // CrossRef search state
  const [searchResults, setSearchResults] = useState<CrossRefMatch[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

  const handleDoiLookup = async () => {
    const trimmed = doiInput.trim();
    if (!trimmed) return;
    setDoiLoading(true);
    setDoiResult(null);
    try {
      const result = await api.addByDoi(trimmed, defaultRefType || undefined, sessionId);
      if (result.already_exists) {
        setDoiResult(`Already in database: ${result.title}`);
      } else {
        setDoiResult(`Added: ${result.title}`);
      }
      onAdded?.(result);
    } catch (e: any) {
      setDoiResult(`Error: ${e.message}`);
    } finally {
      setDoiLoading(false);
    }
  };

  const handleManualSubmit = async () => {
    if (!title.trim()) return;
    setFormLoading(true);
    setFormResult(null);
    try {
      const result = await api.addManual({
        title: title.trim(),
        authors: authors.trim() ? authors.split(/[;,]/).map((a) => a.trim()).filter(Boolean) : [],
        year: year ? parseInt(year) : 0,
        journal: journal.trim() || undefined,
        doi: doi.trim() || undefined,
        ref_type: refType || undefined,
        session_id: sessionId,
      });
      if (result.already_exists) {
        setFormResult(`Already in database: ${result.title}`);
      } else {
        setFormResult(`Added: ${result.title}`);
      }
      onAdded?.(result);
    } catch (e: any) {
      setFormResult(`Error: ${e.message}`);
    } finally {
      setFormLoading(false);
    }
  };

  const handleCrossRefSearch = async () => {
    const query = title.trim() || prefillTitle?.trim();
    if (!query) return;
    setSearchLoading(true);
    setShowSearch(true);
    try {
      const data = await api.crossrefSearch(query, 5);
      setSearchResults(data.results);
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleSelectCrossRef = async (match: CrossRefMatch) => {
    if (!match.doi) return;
    setSearchLoading(true);
    try {
      const result = await api.addByDoi(match.doi, defaultRefType || refType || undefined, sessionId);
      const msg = result.already_exists
        ? `Already in database: ${result.title}`
        : `Added: ${result.title}`;
      setFormResult(msg);
      setShowSearch(false);
      onAdded?.(result);
    } catch (e: any) {
      setFormResult(`Error: ${e.message}`);
    } finally {
      setSearchLoading(false);
    }
  };

  if (compact) {
    return (
      <div className="space-y-2">
        {/* DOI quick-add row */}
        <div className="flex gap-1.5">
          <input
            type="text"
            value={doiInput}
            onChange={(e) => setDoiInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDoiLookup()}
            placeholder="DOI (e.g. 10.1234/...)"
            className="flex-1 bg-bg-primary border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          />
          <button
            onClick={handleDoiLookup}
            disabled={doiLoading || !doiInput.trim()}
            className="px-2 py-1 bg-accent text-text-inverse text-xs rounded hover:bg-accent-dim disabled:opacity-50 transition-colors"
          >
            {doiLoading ? '...' : 'DOI'}
          </button>
          {(prefillTitle || title) && (
            <button
              onClick={handleCrossRefSearch}
              disabled={searchLoading}
              className="px-2 py-1 border border-border text-text-secondary text-xs rounded hover:bg-bg-hover disabled:opacity-50 transition-colors"
            >
              {searchLoading ? '...' : 'Find'}
            </button>
          )}
          <button
            onClick={() => setShowFullForm(!showFullForm)}
            className="px-2 py-1 border border-border text-text-secondary text-xs rounded hover:bg-bg-hover transition-colors"
          >
            {showFullForm ? 'Less' : 'Manual'}
          </button>
        </div>

        {doiResult && (
          <p className={`text-[11px] ${doiResult.startsWith('Error') ? 'text-error' : 'text-success'}`}>
            {doiResult}
          </p>
        )}

        {/* CrossRef search results */}
        {showSearch && (
          <div className="border border-border rounded bg-bg-primary max-h-40 overflow-y-auto">
            {searchLoading ? (
              <div className="p-2 text-xs text-text-muted">Searching CrossRef...</div>
            ) : searchResults.length === 0 ? (
              <div className="p-2 text-xs text-text-muted">No results found</div>
            ) : (
              searchResults.map((m, i) => (
                <button
                  key={i}
                  onClick={() => handleSelectCrossRef(m)}
                  className="w-full text-left p-2 hover:bg-bg-hover border-b border-border last:border-0 transition-colors"
                >
                  <p className="text-xs text-text-primary truncate">{m.title}</p>
                  <p className="text-[10px] text-text-muted">
                    {m.authors.slice(0, 2).join(', ')}{m.authors.length > 2 ? ' et al.' : ''}{' '}
                    {m.year > 0 && `(${m.year})`} {m.journal && `- ${m.journal}`}
                  </p>
                </button>
              ))
            )}
          </div>
        )}

        {/* Compact full form */}
        {showFullForm && (
          <div className="space-y-1.5">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title"
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
            <input
              type="text"
              value={authors}
              onChange={(e) => setAuthors(e.target.value)}
              placeholder="Authors (comma-separated)"
              className="w-full bg-bg-primary border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
            <div className="flex gap-1.5">
              <input
                type="text"
                value={year}
                onChange={(e) => setYear(e.target.value)}
                placeholder="Year"
                className="w-20 bg-bg-primary border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
              />
              <input
                type="text"
                value={journal}
                onChange={(e) => setJournal(e.target.value)}
                placeholder="Journal"
                className="flex-1 bg-bg-primary border border-border rounded px-2 py-1 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
              />
            </div>
            <div className="flex gap-1.5">
              <select
                value={refType}
                onChange={(e) => setRefType(e.target.value)}
                className="flex-1 bg-bg-primary border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent"
              >
                {REF_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <button
                onClick={handleManualSubmit}
                disabled={formLoading || !title.trim()}
                className="px-3 py-1 bg-accent text-text-inverse text-xs rounded hover:bg-accent-dim disabled:opacity-50 transition-colors"
              >
                {formLoading ? '...' : 'Add'}
              </button>
            </div>
            {formResult && (
              <p className={`text-[11px] ${formResult.startsWith('Error') ? 'text-error' : 'text-success'}`}>
                {formResult}
              </p>
            )}
          </div>
        )}
      </div>
    );
  }

  // Full-size layout (for References page)
  return (
    <div className="space-y-4">
      {/* DOI quick-add */}
      <div>
        <label className="text-xs font-medium text-text-muted uppercase tracking-wider">
          Quick Add by DOI
        </label>
        <div className="flex gap-2 mt-1.5">
          <input
            type="text"
            value={doiInput}
            onChange={(e) => setDoiInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDoiLookup()}
            placeholder="Enter DOI (e.g. 10.1234/example)"
            className="flex-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          />
          <button
            onClick={handleDoiLookup}
            disabled={doiLoading || !doiInput.trim()}
            className="px-4 py-2 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 transition-colors"
          >
            {doiLoading ? 'Looking up...' : 'Lookup DOI'}
          </button>
        </div>
        {doiResult && (
          <p className={`text-xs mt-1.5 ${doiResult.startsWith('Error') ? 'text-error' : 'text-success'}`}>
            {doiResult}
          </p>
        )}
      </div>

      {/* Separator */}
      <div className="flex items-center gap-3">
        <div className="flex-1 border-t border-border" />
        <span className="text-xs text-text-muted">or enter details manually</span>
        <div className="flex-1 border-t border-border" />
      </div>

      {/* Manual form */}
      <div className="space-y-3">
        <div>
          <label className="text-xs text-text-muted">Title *</label>
          <div className="flex gap-2 mt-1">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Full title of the work"
              className="flex-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
            {title.trim() && (
              <button
                onClick={handleCrossRefSearch}
                disabled={searchLoading}
                className="px-3 py-2 border border-border text-text-secondary text-sm rounded-lg hover:bg-bg-hover disabled:opacity-50 transition-colors whitespace-nowrap"
              >
                {searchLoading ? 'Searching...' : 'Find on CrossRef'}
              </button>
            )}
          </div>
        </div>

        {/* CrossRef search results */}
        {showSearch && (
          <div className="border border-border rounded-lg bg-bg-primary max-h-48 overflow-y-auto">
            {searchLoading ? (
              <div className="p-3 text-sm text-text-muted">Searching CrossRef...</div>
            ) : searchResults.length === 0 ? (
              <div className="p-3 text-sm text-text-muted">No results found</div>
            ) : (
              searchResults.map((m, i) => (
                <button
                  key={i}
                  onClick={() => handleSelectCrossRef(m)}
                  className="w-full text-left p-3 hover:bg-bg-hover border-b border-border last:border-0 transition-colors"
                >
                  <p className="text-sm text-text-primary">{m.title}</p>
                  <p className="text-xs text-text-muted mt-0.5">
                    {m.authors.slice(0, 3).join(', ')}{m.authors.length > 3 ? ' et al.' : ''}{' '}
                    {m.year > 0 && `(${m.year})`} {m.journal && `- ${m.journal}`}
                    {m.doi && (
                      <span className="text-text-muted/60 ml-2">{m.doi}</span>
                    )}
                  </p>
                </button>
              ))
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted">Authors (comma-separated)</label>
            <input
              type="text"
              value={authors}
              onChange={(e) => setAuthors(e.target.value)}
              placeholder="Author 1, Author 2"
              className="w-full mt-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">Year</label>
            <input
              type="text"
              value={year}
              onChange={(e) => setYear(e.target.value)}
              placeholder="2024"
              className="w-full mt-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted">Journal</label>
            <input
              type="text"
              value={journal}
              onChange={(e) => setJournal(e.target.value)}
              placeholder="Journal name"
              className="w-full mt-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
          </div>
          <div>
            <label className="text-xs text-text-muted">DOI</label>
            <input
              type="text"
              value={doi}
              onChange={(e) => setDoi(e.target.value)}
              placeholder="10.1234/..."
              className="w-full mt-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-text-muted">Reference Type</label>
            <select
              value={refType}
              onChange={(e) => setRefType(e.target.value)}
              className="w-full mt-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              {REF_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={handleManualSubmit}
              disabled={formLoading || !title.trim()}
              className="px-5 py-2 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 transition-colors"
            >
              {formLoading ? 'Adding...' : 'Add Reference'}
            </button>
          </div>
        </div>

        {formResult && (
          <p className={`text-xs ${formResult.startsWith('Error') ? 'text-error' : 'text-success'}`}>
            {formResult}
          </p>
        )}
      </div>
    </div>
  );
}
