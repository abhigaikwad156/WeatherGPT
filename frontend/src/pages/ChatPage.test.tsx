import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, vi } from "vitest";

import { weatherGptApi } from "../api/weatherGpt";
import { ChatPage } from "./ChatPage";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    sendMessage: vi.fn()
  }
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test("shows the returned source title and URL with the assistant answer", async () => {
  const sourceUrl = "https://www.fao.org/el-nino/en";
  vi.mocked(weatherGptApi.sendMessage).mockResolvedValue({
    conversationId: "conversation-1",
    message: {
      id: "message-1",
      role: "assistant",
      content: "FAO recommends anticipatory action.",
      createdAt: "2026-11-20T00:00:00Z",
      metadata: {
        intent: "UNKNOWN",
        knowledgeSources: [{
          source_id: "fao-el-nino-preparedness",
          title: "El Niño | FAO",
          publisher: "Food and Agriculture Organization of the United Nations",
          source_uri: sourceUrl
        }]
      }
    }
  });

  render(<ChatPage />);
  fireEvent.change(screen.getByRole("textbox", { name: "Your weather question" }), {
    target: { value: "How can producers prepare?" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));

  expect(await screen.findByText("FAO recommends anticipatory action.")).toBeInTheDocument();
  expect(screen.getByText("El Niño | FAO")).toBeInTheDocument();
  await waitFor(() => {
    expect(screen.getByRole("link", { name: sourceUrl })).toHaveAttribute("href", sourceUrl);
  });
});
