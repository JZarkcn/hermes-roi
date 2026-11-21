#!/usr/bin/env bash
# 生成"封装版"发布仓库:单提交、署名 owner(Jzarkcn.sg / icespot2005@gmail.com)、无开发历史、无本机 blob。
# 用法: scripts/make-dist.sh  (目标目录默认 <repo 同级>/hermes-roi-dist,可用 HERMES_ROI_DIST 覆盖)
# 注意: file:// 安装时 git 会把克隆来源路径写进接收机的 .git log(那是接收机自己的路径);
#       对第三方分发请用 https 市场 URL/匿名仓库,不暴露任何本机信息。
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_REV="$(git -C "$SRC" rev-parse --short HEAD)"
DIST="${HERMES_ROI_DIST:-$(dirname "$SRC")/hermes-roi-dist}"

rm -rf "$DIST"
mkdir -p "$DIST"
git -C "$SRC" archive HEAD | tar -x -C "$DIST"

git -C "$DIST" init -q
git -C "$DIST" config user.name "Jzarkcn.sg"
git -C "$DIST" config user.email "icespot2005@gmail.com"
git -C "$DIST" add -A
git -C "$DIST" commit -q -m "release: hermes-roi @ ${SRC_REV}"
echo "dist: $DIST  (single commit @ ${SRC_REV})"
