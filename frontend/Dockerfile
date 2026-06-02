FROM node:22-alpine

ENV NODE_ENV=development

WORKDIR /app

RUN apk add --no-cache curl

# Install dependencies from the lockfile for reproducible builds.
COPY package.json package-lock.json* ./
RUN npm ci || npm install

COPY . .

# Drop privileges: the node image ships an unprivileged `node` user.
RUN chown -R node:node /app
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:3000 || exit 1

CMD ["npm", "run", "dev"]
