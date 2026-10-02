# The web image (ADR-032). Build from the repo root:
#   docker build -f apps/web/Dockerfile --build-arg SITE_URL=https://cornerpin.app -t cornerpin-web .
# Next's standalone server on $PORT. SITE_URL is baked into pages prerendered at build.

FROM node:24-slim AS build
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter web
COPY apps/web apps/web
ARG SITE_URL=https://cornerpin.app
ENV SITE_URL=$SITE_URL NEXT_OUTPUT=standalone
RUN pnpm --filter web build

FROM node:24-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=8080 HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=node:node /repo/apps/web/public ./apps/web/public
USER node
CMD ["node", "apps/web/server.js"]
