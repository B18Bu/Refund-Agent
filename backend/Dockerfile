FROM python:3.11-slim

# 中文 locale + 基础工具
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

# PaddlePaddle / OpenCV 所需的系统库（slim 镜像缺失 libgomp，OCR 推理会失败）
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 \
 && rm -rf /var/lib/apt/lists/*

# 先装基础依赖（含 OCR 依赖，本地推理引擎）
COPY requirements.txt requirements-ocr.txt ./
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple setuptools \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-ocr.txt

# PaddleOCR 2.x 会将 NumPy 降到 1.x；同步固定兼容的 ml-dtypes，避免 pip check 冲突。
RUN pip install --no-cache-dir --retries 10 --timeout 300 -i https://pypi.tuna.tsinghua.edu.cn/simple "ml-dtypes<0.6"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
