#!/usr/bin/env bash
# 构建生产镜像脚本
#   ./build.sh                       # 使用 core/ver.py 中的版本号构建
#   ./build.sh -v 2.2.1              # 指定版本号构建 v2.2.1
#   ./build.sh -v 2.2.1 -w           # 先编译前端发布到 static 再构建
#   ./build.sh -v 2.2.1 -p           # 构建并推送到镜像仓库
set -e

# 切换到脚本所在目录，保证在任意目录执行都正常
cd "$(dirname "$0")"

# 镜像仓库配置
REGISTRY="crpi-qp8hiqijfnilf93t.cn-hangzhou.personal.cr.aliyuncs.com"
IMAGE_NAME="${REGISTRY}/bulexu/we-mp-rss"
PLATFORM="${PLATFORM:-linux/amd64}"
DOCKERFILE="${DOCKERFILE:-./Dockerfile}"

usage() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  -v, --version <版本号>   指定镜像版本号（默认读取 core/ver.py）"
    echo "  -w, --web                发布前端（编译 web_ui 并复制到 static）"
    echo "  -p, --push               构建完成后推送到镜像仓库"
    echo "      --platform <平台>     构建平台（默认 linux/amd64）"
    echo "  -h, --help               显示帮助"
    echo ""
    echo "示例:"
    echo "  $0 -v 2.2.1 -w"
    echo "  $0 -v 2.2.1 -w -p"
}

VERSION=""
PUBLISH_WEB=0
PUSH_IMAGE=0

# 解析参数
while [ $# -gt 0 ]; do
    case "$1" in
        -v|--version)
            VERSION="$2"
            if [ -z "$VERSION" ]; then
                echo "错误: -v 需要指定版本号"
                exit 1
            fi
            shift 2
            ;;
        --version=*)
            VERSION="${1#*=}"
            shift
            ;;
        -w|--web)
            PUBLISH_WEB=1
            shift
            ;;
        -p|--push)
            PUSH_IMAGE=1
            shift
            ;;
        --platform)
            PLATFORM="$2"
            if [ -z "$PLATFORM" ]; then
                echo "错误: --platform 需要指定平台"
                exit 1
            fi
            shift 2
            ;;
        --platform=*)
            PLATFORM="${1#*=}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "错误: 未知参数 $1"
            usage
            exit 1
            ;;
    esac
done

# 未指定版本号时，从 core/ver.py 读取
if [ -z "$VERSION" ]; then
    VERSION=$(sed -n "s/^VERSION *= *'\([^']*\)'.*/\1/p" core/ver.py | head -n 1)
    if [ -z "$VERSION" ]; then
        echo "错误: 无法从 core/ver.py 读取版本号"
        exit 1
    fi
fi

# 统一 tag 格式，带 v 前缀
case "$VERSION" in
    v*) TAG="$VERSION" ;;
    *)  TAG="v$VERSION" ;;
esac

# 是否发布前端
if [ "$PUBLISH_WEB" = "1" ]; then
    if ! command -v yarn >/dev/null 2>&1; then
        echo "错误: 未找到 yarn，无法编译前端"
        exit 1
    fi
    echo "==> 编译前端并发布到 static 目录..."
    (cd web_ui && bash build.sh)
fi

# 构建镜像
echo "==> 构建镜像: $IMAGE_NAME:$TAG (平台: $PLATFORM)"

BUILD_ARGS=(
    --platform "$PLATFORM"
    -f "$DOCKERFILE"
    -t "$IMAGE_NAME:$TAG"
    -t "$IMAGE_NAME:latest"
)

if [ "$PUSH_IMAGE" = "1" ]; then
    BUILD_ARGS+=(--push)
else
    BUILD_ARGS+=(--load)
fi

docker buildx build "${BUILD_ARGS[@]}" .

echo "==> 构建完成: $IMAGE_NAME:$TAG"
if [ "$PUSH_IMAGE" != "1" ]; then
    echo "如需推送，请执行:"
    echo "  docker push $IMAGE_NAME:$TAG"
    echo "  docker push $IMAGE_NAME:latest"
fi
