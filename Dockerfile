FROM public.ecr.aws/lambda/python:3.13-arm64@sha256:241d405a4355398ee53fedeba1091a150a06fd4d47c8b7977931db1c1ea10e33
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 LANG=C.UTF-8 LC_ALL=C.UTF-8 LANGUAGE=C
RUN dnf upgrade -y && dnf clean all && printf 'appuser:x:10001:10001:Runtime:/tmp:/sbin/nologin\n' >> /etc/passwd && printf 'appuser:x:10001:\n' >> /etc/group
WORKDIR /app
COPY requirements-demo.lock.txt ./
RUN pip install --no-cache-dir -r requirements-demo.lock.txt
COPY analysis_engine ./analysis_engine
COPY app/CloudDataScientist ./app/CloudDataScientist
USER 10001:10001
EXPOSE 8080
ENTRYPOINT []
CMD ["python", "-m", "app.CloudDataScientist.main"]
