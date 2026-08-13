import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/app/routeTree.gen.ts", "coverage"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked, ...tseslint.configs.stylisticTypeChecked],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // "No use of any" — belt and suspenders on top of strictTypeChecked.
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unsafe-assignment": "error",
      "@typescript-eslint/no-unsafe-member-access": "error",
      "@typescript-eslint/no-unsafe-call": "error",
      "@typescript-eslint/no-unsafe-return": "error",
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
  {
    // Test files: relax a couple of stylistic rules that fight test ergonomics.
    files: ["**/*.test.{ts,tsx}", "src/test/**"],
    rules: {
      "@typescript-eslint/no-non-null-assertion": "off",
      // Fake/mock classes (e.g. a stubbed `WebSocket`) legitimately
      // implement methods as intentional no-ops.
      "@typescript-eslint/no-empty-function": "off",
    },
  },
  {
    // Route files (TanStack Router's file-based routing convention):
    // every file exports a non-component `Route` object alongside any
    // local page components, and `beforeLoad` legitimately throws
    // `redirect()`/`notFound()` — a `Response`, not an `Error` — which
    // the router itself catches by type, not by `instanceof Error`.
    files: ["src/pages/**/*.{ts,tsx}"],
    rules: {
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/only-throw-error": "off",
    },
  },
  {
    // `requirePermission` is a `beforeLoad` guard factory used by route
    // files but defined outside `src/pages/` — same "throws a Response,
    // not an Error" reasoning as the override above.
    files: ["src/lib/permissions.ts"],
    rules: {
      "@typescript-eslint/only-throw-error": "off",
    },
  },
);
