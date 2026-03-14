# Build stage
FROM node:18-alpine as builder

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

RUN npm run build

# Development/Production stage
FROM node:18-alpine

WORKDIR /app

# Install both dev and production dependencies
COPY package*.json ./
RUN npm install

# Copy built files from builder
COPY --from=builder /app/dist ./dist

# Install serve for production fallback
RUN npm install -g serve

EXPOSE 5173

# Use dev by default, can be overridden in docker-compose
CMD ["npm", "run", "dev"]
