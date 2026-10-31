FROM docker.io/library/python:3.13-slim@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 LANG=C.UTF-8 LC_ALL=C.UTF-8 LANGUAGE=C
RUN apt-get update && apt-get upgrade -y && apt-get clean
WORKDIR /app
COPY requirements-demo.lock.txt ./
RUN pip install --no-cache-dir -r requirements-demo.lock.txt && useradd --create-home --uid 10001 appuser
COPY analysis_engine ./analysis_engine
COPY app/CloudDataScientist ./app/CloudDataScientist
USER appuser
EXPOSE 8080
CMD ["python", "-m", "app.CloudDataScientist.main"]
