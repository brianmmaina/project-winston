/** Loading / error placeholders: error panel, empty message, and reusable card skeletons. */

import type { ReactElement, ReactNode } from "react";

interface PageStateProps {
  error: string | null;
  onRetry?: () => void;
  emptyMessage?: string | null;
  children: ReactNode;
}

export function PageState({ error, onRetry, emptyMessage, children }: PageStateProps): ReactElement | null {
  if (error) {
    return (
      <div className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-6 text-rose-100">
        <p className="font-medium">Something went wrong</p>
        <p className="mt-2 text-sm text-rose-200/90">{error}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-500"
          >
            Retry
          </button>
        ) : null}
      </div>
    );
  }
  if (emptyMessage) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-8 text-center text-slate-300">
        {emptyMessage}
      </div>
    );
  }
  return <>{children}</>;
}

export function CardSkeletonGrid({ count = 6 }: { count?: number }): ReactElement {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-xl border border-slate-800 bg-slate-900/50 p-5">
          <div className="h-4 w-1/3 rounded bg-slate-700" />
          <div className="mt-4 h-32 rounded bg-slate-800" />
        </div>
      ))}
    </div>
  );
}

export function DetailSkeleton(): ReactElement {
  return (
    <div className="space-y-6">
      <div className="h-40 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50" />
      <div className="h-64 animate-pulse rounded-xl border border-slate-800 bg-slate-900/50" />
    </div>
  );
}
