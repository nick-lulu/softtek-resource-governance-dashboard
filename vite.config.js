import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Actions supplies the current repository name, including after a rename.
const repositoryName = process.env.GITHUB_REPOSITORY?.split("/")[1];

export default defineConfig({
  base: `/${repositoryName || "scm-corporate-resource-governance-dashboard"}/`,
  plugins: [react()],
});
