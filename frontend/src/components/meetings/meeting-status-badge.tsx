import type { MeetingStatus } from "@/types/database";
import { formatMeetingStatus } from "@/lib/meetings";

const statusStyles: Record<MeetingStatus, string> = {
  draft: "bg-zinc-100 text-zinc-700",
  processing: "bg-blue-100 text-blue-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export function MeetingStatusBadge({ status }: { status: MeetingStatus }) {
  return (
    <span
      className={`inline-flex shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${statusStyles[status]}`}
    >
      {formatMeetingStatus(status)}
    </span>
  );
}
