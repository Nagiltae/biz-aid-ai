# 질문 처리 전용 FastAPI 이미지(IMP-017). 의존성만 담고 코드·계약·모델은 compose가 읽기 전용으로 mount한다.
# 파싱·인덱싱 배치는 host에서 requirements.txt 환경으로 실행한다. 의존성이 바뀔 때만 다시 빌드한다.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONPATH=/app/data-pipeline/src

COPY requirements-api.txt /tmp/requirements-api.txt
# WHY: PyPI의 linux torch는 CUDA 라이브러리(수 GB)를 함께 받는다. 질문 서버는 CPU 추론만 하므로 같은 버전의 CPU 전용 build를 먼저 깐다.
# requirements-api.txt의 torch==2.14.0은 2.14.0+cpu로 충족된다(PEP 440). embedding_key는 공개 버전(2.14.0)만 쓴다.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0+cpu \
    && pip install -r /tmp/requirements-api.txt && rm /tmp/requirements-api.txt \
    && useradd --create-home --uid 10001 bizaid

WORKDIR /app
USER bizaid
EXPOSE 8000

# 컨테이너 안에서는 compose 네트워크(backend)가 부를 수 있게 0.0.0.0에 연다. host 공개는 compose가 127.0.0.1:8000으로만 한다.
CMD ["uvicorn", "biz_aid_pipeline.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--reload", "--reload-dir", "/app/data-pipeline/src"]
