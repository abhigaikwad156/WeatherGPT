import type { PropsWithChildren, ReactNode } from "react";

export function Card({ children, className = "", id }: PropsWithChildren<{ className?: string; id?: string }>) {
  return <section id={id} className={`card ${className}`}>{children}</section>;
}

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return <div className="state loading" role="status">{label}</div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="state empty"><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="state error" role="alert"><h3>Unable to load information</h3><p>{message}</p>{retry && <button onClick={retry}>Try again</button>}</div>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`badge badge-${severity}`}>{severity}</span>;
}
