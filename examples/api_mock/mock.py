"""
Alphora API Mock 示例

启动：
    python -m examples.api_mock.mock --host 0.0.0.0 --port 8000

前端联调：
    Endpoint: /api/v1/chat/completions
    兼容路径: /alphadata/chat/completions
"""

from __future__ import annotations

import argparse
import asyncio

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from alphora.server.openai_request_body import OpenAIRequest
from alphora.server.stream_responser import DataStreamer

APP_TITLE = "Alphora API Mock"
MOCK_MODEL = "AlphaData-Mock"

app = FastAPI(title=APP_TITLE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _emit_mock_stream(streamer: DataStreamer, request: OpenAIRequest) -> None:
    """模拟流式输出，帮助前端实现实时渲染逻辑。"""
    query = request.get_user_query().strip() or "你好"
    await streamer.send_data("thinking", f"收到问题: {query}")
    await asyncio.sleep(0.05)
    await streamer.send_data("text", "这是一个 mock 响应，用于前端联调。")
    await asyncio.sleep(0.05)
    await streamer.send_data("code", "console.log('hello from mock');")
    await streamer.stop("stop")


async def _build_non_stream_response(request: OpenAIRequest):
    """生成非流式完整响应，格式与服务端一致。"""
    streamer = DataStreamer(timeout=30, model_name=MOCK_MODEL)
    query = request.get_user_query().strip() or "你好"
    await streamer.send_data("thinking", f"收到问题: {query}")
    await streamer.send_data("text", "这是一个 mock 响应，用于前端联调。")
    await streamer.send_data("code", "console.log('hello from mock');")
    await streamer.stop("stop")
    return await streamer.start_non_streaming_openai()


@app.post("/api/v1/chat/completions")
@app.post("/alphadata/chat/completions")
async def chat_completions(body: OpenAIRequest, raw_request: Request):
    _ = raw_request  # 保留参数便于后续扩展
    if body.stream:
        streamer = DataStreamer(timeout=30, model_name=MOCK_MODEL)
        asyncio.create_task(_emit_mock_stream(streamer, body))
        return streamer.start_streaming_openai()
    return await _build_non_stream_response(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Alphora API Mock")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
