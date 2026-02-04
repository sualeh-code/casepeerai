FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (System deps are already in the base image)
RUN playwright install chromium

# Copy application code
COPY . .

# Expose port and start the application
EXPOSE 8000
CMD ["uvicorn", "caseapi:app", "--host", "0.0.0.0", "--port", "8000"]
