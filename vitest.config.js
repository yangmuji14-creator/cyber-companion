import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["webui/static/modules/__tests__/**/*.test.js"],
    clearMocks: true,
    restoreMocks: true,
  },
});
