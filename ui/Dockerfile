# Dev-oriented image: the source is bind-mounted by docker-compose, so this
# exists to own node_modules and give a consistent Node version, not to produce
# a production bundle. A multi-stage build + nginx comes with deployment.
FROM node:22-alpine

WORKDIR /app

# Copy manifests first so `npm ci` is cached independently of source changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
