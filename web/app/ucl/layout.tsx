import Link from "next/link";
import { UclTabs } from "@/components/UclTabs";

export default function UclLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Champions League Fantasy</h1>
        <Link href="/settings" className="text-sm text-[var(--muted)]">
          Settings
        </Link>
      </div>
      <UclTabs />
      {children}
    </div>
  );
}
