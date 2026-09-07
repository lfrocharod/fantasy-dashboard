import type { ReactNode } from "react";
import { NflTabs } from "./NflTabs";

export default function NflLayout({ children }: { children: ReactNode }) {
  return (
    <div className="space-y-4">
      <NflTabs />
      {children}
    </div>
  );
}
