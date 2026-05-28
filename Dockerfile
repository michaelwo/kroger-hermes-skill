FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/openai/codex-universal.git /opt/codex-universal

WORKDIR /workspace

ENV PYTHONUNBUFFERED=1
ENV OPENAI_API_KEY=""

CMD ["/bin/bash"]
