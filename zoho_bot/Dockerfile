FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /repos
COPY . /repos/Stock-Planning
RUN git init boe-cost-calculator && cd boe-cost-calculator && git remote add origin https://github.com/thakorakash04-cell/boe-cost-calculator.git && git fetch --depth 1 origin c7b37e5e2d6d8ca0a5418a1f103990e51bdaa056 && git checkout FETCH_HEAD && rm -rf .git
RUN git init meddevice-research-platform && cd meddevice-research-platform && git remote add origin https://github.com/thakorakash04-cell/meddevice-research-platform.git && git fetch --depth 1 origin a1abc85b024c13749d5da66bc27d0da15790f923 && git checkout FETCH_HEAD && rm -rf .git
RUN git init awc-platform && cd awc-platform && git remote add origin https://github.com/thakorakash04-cell/awc-platform.git && git fetch --depth 1 origin 082529caf7df7b3a4453cae3e43355394facf0f1 && git checkout FETCH_HEAD && rm -rf .git
RUN pip install --no-cache-dir -r /repos/Stock-Planning/zoho_bot/requirements.txt
WORKDIR /repos/Stock-Planning/zoho_bot
ENV REPOS_ROOT=/repos
CMD ["sh", "-c", "uvicorn service:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
