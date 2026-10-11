import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { router } from "./routes";
import "./index.css";

// After a deploy, a tab still running the previous build asks for chunks that
// no longer exist. Reload once to pick up the new build; if that just happened,
// let the error show instead of looping.
window.addEventListener("vite:preloadError", (event) => {
  const key = "fantasy:chunk-reload";
  try {
    if (Date.now() - Number(sessionStorage.getItem(key) ?? 0) < 10_000) return;
    sessionStorage.setItem(key, String(Date.now()));
  } catch {
    return; // no storage, no loop guard: don't reload
  }
  event.preventDefault();
  window.location.reload();
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // a 401 redirects to the login page; don't retry it
      retry: (count, error) => count < 2 && (error as { status?: number })?.status !== 401,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
