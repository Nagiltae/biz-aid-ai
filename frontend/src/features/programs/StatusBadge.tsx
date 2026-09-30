import type { RecruitmentStatus } from "./programsApi";

export function StatusBadge({ status, label }: { status: RecruitmentStatus; label: string }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{label}</span>;
}
