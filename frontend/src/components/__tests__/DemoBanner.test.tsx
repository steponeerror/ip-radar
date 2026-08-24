import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { DemoBanner } from "../DemoBanner";
import { renderWithI18n } from "../../test/i18nTestUtils";

describe("DemoBanner", () => {
  it("renders message with GitHub link", () => {
    renderWithI18n(<DemoBanner />);
    expect(screen.getByText(/demo/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /github/i });
    expect(link).toHaveAttribute(
      "href", "https://github.com/steponeerror/ip-radar",
    );
  });
});
