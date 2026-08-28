FROM python:3.11-slim

# 中文 locale + 基础工具
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

# PaddlePaddle / OpenCV 所需的系统库（slim 镜像缺失 libgomp，OCR 推理会失败）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# 先装基础依赖（含 OCR 依赖，本地推理引擎）
COPY requirements.txt requirements-ocr.txt ./
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple setuptools \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt \
 && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-ocr.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
