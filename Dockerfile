FROM python:3.12-slim

# Install Node.js 22 (LTS) + npm
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Codex CLI
RUN npm install -g @openai/codex \
    || (curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh)

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
ENV OPENAI_API_KEY=""

CMD ["/bin/bash"]
