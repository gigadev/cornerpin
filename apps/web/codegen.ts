import type { CodegenConfig } from "@graphql-codegen/cli";

// Types for the public GraphQL API (ADR-007). The schema comes from the API (pnpm gen:api);
// queries live in lib/graphql/*.graphql.
const config: CodegenConfig = {
  schema: "lib/graphql/schema.graphql",
  documents: "lib/graphql/*.graphql",
  generates: {
    "lib/graphql/generated.ts": {
      plugins: ["typescript-operations", "typed-document-node"],
      config: {
        enumsAsTypes: true,
        useTypeImports: true,
        avoidOptionals: { field: true },
        scalars: {
          GeoJSON: {
            input: "import('geojson').MultiPolygon",
            output: "import('geojson').MultiPolygon",
          },
        },
      },
    },
  },
};

export default config;
