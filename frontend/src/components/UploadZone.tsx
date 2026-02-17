'use client';

import { useState, useCallback, useRef } from 'react';
import { api } from '@/lib/api';

interface Props {
  onUpload?: (result: any) => void;
  sessionId?: string;
}

export default function UploadZone({ onUpload, sessionId }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<{ name: string; ok: boolean; msg: string }[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const pdfFiles = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfFiles.length === 0) return;

    setUploading(true);
    const newResults: typeof results = [];

    for (const file of pdfFiles) {
      try {
        const res = await api.uploadPdf(file, sessionId);
        newResults.push({ name: file.name, ok: res.indexed, msg: res.indexed ? 'Indexed' : res.error || 'Failed' });
        onUpload?.(res);
      } catch (e: any) {
        newResults.push({ name: file.name, ok: false, msg: e.message });
      }
    }

    setResults(prev => [...newResults, ...prev]);
    setUploading(false);
  }, [onUpload]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${
          dragOver
            ? 'border-accent bg-accent-light'
            : 'border-border hover:border-border-strong'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          multiple
          className="hidden"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
        {uploading ? (
          <p className="text-sm text-accent">Uploading & indexing...</p>
        ) : (
          <>
            <svg className="w-8 h-8 mx-auto mb-2 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-sm text-text-secondary">Drop PDF files here or click to browse</p>
            <p className="text-xs text-text-muted mt-1">Files will be indexed into ChromaDB</p>
          </>
        )}
      </div>

      {results.length > 0 && (
        <div className="space-y-1">
          {results.slice(0, 5).map((r, i) => (
            <div key={i} className={`text-xs px-3 py-1.5 rounded flex items-center gap-2 ${
              r.ok ? 'bg-success/10 text-success' : 'bg-error/10 text-error'
            }`}>
              <span>{r.ok ? '\u2713' : '\u2717'}</span>
              <span className="truncate">{r.name}</span>
              <span className="text-text-muted ml-auto flex-shrink-0">{r.msg}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
