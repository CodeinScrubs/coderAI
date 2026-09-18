FROM python:3.12-slim

# Install system dependencies needed for compiling python packages, git, and nodejs for checking syntax
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV WEB_APP_HOST=0.0.0.0
ENV WEB_APP_PORT=7864

EXPOSE 7864

CMD ["python", "launcher.py"]
