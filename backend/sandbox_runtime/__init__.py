"""独立分析沙箱的最小运行时。

这个包会被 Web 镜像和 sandbox 镜像同时使用；sandbox 镜像不会复制 app/，
因此天然无法 import 数据库、鉴权、COS 或 AI 客户端。
"""
