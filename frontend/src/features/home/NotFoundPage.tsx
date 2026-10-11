import { Link } from "react-router";
import { EmptyState } from "@/shared/ui";

export default function NotFoundPage() {
  return (
    <EmptyState
      title="Nothing here"
      hint={
        <Link to="/" className="text-[var(--accent)]">
          Back to the command centre
        </Link>
      }
    />
  );
}
