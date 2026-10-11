import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { Checklist, QueryView, Range, Toggle } from "./ui";

describe("Toggle", () => {
  it("marks the active option and reports clicks", () => {
    const onChange = vi.fn();
    render(<Toggle value="att" options={["att", "def"] as const} label={(v) => v.toUpperCase()} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "ATT" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "DEF" }));
    expect(onChange).toHaveBeenCalledWith("def");
  });
});

describe("QueryView", () => {
  it("shows a skeleton, then the error, then the data", () => {
    const { rerender } = render(
      <QueryView query={{ isPending: true, error: null }}>{(d: string) => <p>{d}</p>}</QueryView>,
    );
    expect(screen.getByLabelText("loading")).toBeInTheDocument();
    rerender(<QueryView query={{ isPending: false, error: new Error("boom") }}>{(d: string) => <p>{d}</p>}</QueryView>);
    expect(screen.getByText("boom")).toBeInTheDocument();
    rerender(<QueryView query={{ isPending: false, error: null, data: "ready" }}>{(d: string) => <p>{d}</p>}</QueryView>);
    expect(screen.getByText("ready")).toBeInTheDocument();
  });
});

describe("Checklist", () => {
  it("links only the items that still need doing", () => {
    render(
      <MemoryRouter>
        <Checklist
          items={[
            { ok: true, text: "Captain set", href: "/ucl/optimizer" },
            { ok: false, text: "2 starters doubtful", href: "/ucl/players", linkText: "fix →" },
          ]}
        />
      </MemoryRouter>,
    );
    expect(screen.getAllByText("OK")).toHaveLength(1);
    expect(screen.getAllByText("DO")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "fix →" })).toHaveAttribute("href", "/ucl/players");
    expect(screen.queryAllByRole("link")).toHaveLength(1);
  });
});

describe("Range", () => {
  it("hides an empty band", () => {
    render(<Range lo={0} hi={0} />);
    expect(screen.getByText("–")).toBeInTheDocument();
  });
});
