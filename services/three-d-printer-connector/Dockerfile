FROM node:22-bookworm-slim
WORKDIR /app
COPY --chown=node:node package.json ./
COPY --chown=node:node src ./src
USER node
ENV NODE_ENV=production
CMD ["node", "src/main.mjs"]
