// @ts-check
import { defineConfig } from "astro/config";
import react from "@astrojs/react";

// Static by default, dynamic by necessity (DESIGN.md D2): pages render on the
// server; React islands hydrate only where interaction demands them.
export default defineConfig({
  output: "static",
  integrations: [react()],
});
