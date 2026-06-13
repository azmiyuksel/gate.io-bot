# --- Build stage ---
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=${BACKEND_URL}
RUN npm run build

# --- Production stage ---
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

RUN apk add --no-cache curl

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:3000 || exit 1

CMD ["node", "server.js"]
