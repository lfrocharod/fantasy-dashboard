import type { ReactNode } from "react";
import { FplTabs } from "./FplTabs";

export default function FplLayout({ children }: { children: ReactNode }) {
  return (
    <div className="space-y-4">
      <FplTabs />
      {children}
    </div>
  );
}
