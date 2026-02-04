# Build Stage for Frontend
FROM node:20-slim AS build-stage
WORKDIR /dashboard
COPY dashboard/package*.json ./
RUN npm install
COPY dashboard/ .
RUN npm run build

# Final Stage
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy
WORKDIR /app

# Copy built frontend assets
COPY --from=build-stage /dashboard/dist ./dashboard/dist

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application code
COPY . .

# Expose port and start the application
EXPOSE 8000
CMD ["uvicorn", "caseapi:app", "--host", "0.0.0.0", "--port", "8000"]
