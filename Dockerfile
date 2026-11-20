FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/models RERANK_MODEL=cross-encoder/ms-marco-TinyBERT-L2-v2
WORKDIR /gather
COPY requirements.txt requirements-semantic.txt requirements.lock ./
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements-semantic.txt
RUN useradd --uid 10001 --create-home gather && mkdir /data /models && chown gather:gather /data /models
COPY --chown=gather:gather app.py start.py search_quality.py ./
COPY --chown=gather:gather capstone ./capstone
COPY --chown=gather:gather static ./static
ENV KNOWLEDGE_DATA_DIR=/data
USER gather
CMD ["python", "start.py", "--host", "0.0.0.0"]
