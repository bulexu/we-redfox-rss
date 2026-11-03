# 使用 Debian 12 (bookworm)：包名与项目 install.sh 兼容 (libgtk-3-0/libasound2)；
# 拉取走本机 registry mirror，避免 ghcr 慢速。
FROM python:3.13-slim-bookworm

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    BROWSER_TYPE=webkit

WORKDIR /app

# 改用国内 Debian 源，加速系统依赖安装
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list /etc/apt/sources.list.d/*.sources 2>/dev/null || true

# 只安装 Playwright WebKit 及其系统依赖。
# 浏览器路径与运行时 install.sh 的计算结果保持一致，避免下游重复下载。
RUN apt-get update \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && pip install playwright==1.55.0 \
    && plantform="$(uname -m)" \
    && PLAYWRIGHT_BROWSERS_PATH="/app/env/driver/_${plantform}" \
        playwright install --with-deps webkit \
    && rm -rf /var/lib/apt/lists/* /root/.cache/pip /tmp/*
