FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --registry=https://registry.npmjs.org --fetch-retries=10 --fetch-retry-mintimeout=1000 --fetch-retry-maxtimeout=60000 --fetch-timeout=300000
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
