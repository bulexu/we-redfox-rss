#!/bin/bash
# 编译前端并替换 static 目录下的旧文件

set -e

# 切换到脚本所在目录，保证在任意目录执行都正常
cd "$(dirname "$0")"

# 设置路径变量
DIST_DIR="dist"
TARGET_DIR="../static"

yarn install
# 执行构建
yarn build

# 同步构建产物到 static 目录，并删除旧版本残留的文件
echo "正在同步构建文件到$TARGET_DIR..."
rsync -a --delete "$DIST_DIR/" "$TARGET_DIR/"
