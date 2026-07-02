FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json nx.json tsconfig.base.json ./
COPY packages ./packages
COPY apps/frontend ./apps/frontend
RUN npm ci
RUN npx nx run frontend:build

FROM nginx:1.27-alpine
COPY --from=build /app/dist/apps/frontend /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
