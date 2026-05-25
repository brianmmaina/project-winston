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
      <div className="border border-error/30 bg-error/10 p-6">
        <p className="font-mono text-[11px] font-bold tracking-[0.06em] uppercase text-error">Error</p>
        <p className="mt-2 font-mono text-[12px] text-error/80">{error}</p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 px-4 py-2 border border-error/40 font-mono text-[10px] font-bold tracking-[0.06em] uppercase text-error hover:bg-error/10 transition-colors"
          >
            Retry
          </button>
        ) : null}
      </div>
    );
  }
  if (emptyMessage) {
    return (
      <div className="border border-outline-variant bg-surface-container py-12 text-center">
        <p className="font-mono text-[12px] text-on-surface-variant">{emptyMessage}</p>
      </div>
    );
  }
  return <>{children}</>;
}

export function CardSkeletonGrid({ count = 6 }: { count?: number }): ReactElement {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="animate-pulse border border-outline-variant bg-surface-container p-5 h-28" />
      ))}
    </div>
  );
}

export function DetailSkeleton(): ReactElement {
  return (
    <div className="space-y-4">
      <div className="h-32 animate-pulse border border-outline-variant bg-surface-container" />
      <div className="h-64 animate-pulse border border-outline-variant bg-surface-container" />
    </div>
  );
}
