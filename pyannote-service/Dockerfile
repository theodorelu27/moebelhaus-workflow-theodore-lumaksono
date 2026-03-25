FROM python:3.10-slim-bullseye

WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    python-multipart

RUN pip install --no-cache-dir \
    torch==2.1.0 torchaudio==2.1.0 \
    --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Patch the np.NaN issue
RUN sed -i 's/np\.NaN/np.nan/g' \
    /usr/local/lib/python3.10/site-packages/pyannote/audio/core/inference.py

RUN pip install --no-cache-dir "numpy==1.26.4"

COPY main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]