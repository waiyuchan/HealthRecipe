FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 recipe
COPY src ./src
COPY web ./web
COPY data/recipes.json data/nutrition.json ./data/
RUN chown -R recipe:recipe /app
USER recipe
ENV HEALTHRECIPE_DB=/app/data/healthrecipe.db
VOLUME ["/app/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
