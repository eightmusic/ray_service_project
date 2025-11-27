# Ray Service 项目框架

该项目提供一个基于 **Ray Serve** 的算法服务框架，具备以下能力：

- 统一的模型入口：通过模型名路由到本地模型或外部 API。
- 使用 Redis 追踪任务消息、并支持心跳检测。
- 按模型维度控制并发与资源（GPU）配置。
- 框架化代码，便于快速接入新的算法。

## 快速开始

1. 安装依赖（推荐 Python 3.10+）：

   ```bash
   pip install --upgrade pip
   pip install poetry
   poetry install
   ```

2. 准备 Redis 服务（示例）：

   ```bash
   docker run -p 6379:6379 redis:7
   ```

3. 配置环境变量（可以复制 `.env.example`）：

   ```bash
   cp .env.example .env
   ```

4. 启动 Ray Serve 应用：

   ```bash
   poetry run python -m ray_service.run
   ```

5. 调用接口（同步）：

   ```bash
   curl -X POST "http://127.0.0.1:8000/invoke/local-echo" \
     -H "Content-Type: application/json" \
     -d '{"payload": {"text": "hello"}}'
   ```

   使用异步模式：

   ```bash
   curl -X POST "http://127.0.0.1:8000/tasks/local-echo" \
     -H "Content-Type: application/json" \
     -d '{"payload": {"text": "hello"}}'
   # 返回 {"task_id": "...", "status": "queued"}
   curl "http://127.0.0.1:8000/tasks/<task_id>"
   ```

## 目录结构

- `ray_service/config.py`：全局设置与模型注册。
- `ray_service/task_queue.py`：Redis 任务消息工具。
- `ray_service/heartbeat.py`：心跳上报与检测。
- `ray_service/models/`：本地模型与外部 API 适配器示例。
- `ray_service/service.py`：Ray Serve 部署、模型路由、并发与 GPU 配置。
- `ray_service/run.py`：启动入口。

示例模型：

- `local-echo`：简单回显。
- `external-sentiment`：演示外部 REST API。
- `nanobanana-image`：调用 NanoBanana 图像生成 API（需要配置 `NANOBANANA_API_KEY`）。

## 扩展指引

1. 在 `config.py` 的 `MODEL_REGISTRY` 添加新的模型配置。
2. 编写对应的本地模型类或外部 API 适配器。
3. 通过 `ray_service.run` 重新部署，即可自动接入新能力。

### 模型配置参数

- `max_concurrency`：单个模型的全局并发上限（同步与异步请求共用）。若希望“每个 worker 允许 N 个并发”，可设置 `max_concurrency = num_workers * N`。
- `num_workers`：为该模型创建的 Ray worker 数量。本地模型会启动多个 `LocalModelWorker`，外部 API 则创建多个 `ExternalModelWorker`，按轮询分配请求。
- `num_cpus` / `num_gpus`：Ray 资源声明。`num_cpus` 同样适用于外部 API 模型，可设为较小值（如 0.25）以便更细粒度调度；`num_gpus` 仅对本地模型有效。

## 同步与异步模式

- `POST /invoke/{model_name}`：同步调用，等待算法执行完毕后一次性返回结果，适用于实时场景。
- `POST /tasks/{model_name}`：异步提交任务，立即返回 `task_id`；后台在 Ray Serve 内调度执行。
- `GET /tasks/{task_id}`：查询任务状态与结果，数据来源于 Redis（`ray_service:task:{task_id}`）。

### NanoBanana 图像生成示例

```bash
export NANOBANANA_API_KEY=实际密钥

curl -X POST "http://127.0.0.1:8000/invoke/nanobanana-image" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "cute corgi astronaut",
    "image_urls": ["https://example.com/reference.jpg"],
    "size": "3:4"
  }'
```

### 同步调用示例

```python
import requests

payload = {
    "prompt": "把这件衣服变成长款",
    "image_urls": [
        "https://huayiyi-ai.oss-cn-shanghai.aliyuncs.com/test_tmp/1759117633476-2c4e21c7-e358-49c8-b280-adee0df10cec.png"
    ],
    "size": "3:4",  # 可选，不填默认为 1:1
}

resp = requests.post(
    "http://127.0.0.1:8000/invoke/nanobanana-image",
    json=payload,
    timeout=120,
)
resp.raise_for_status()
data = resp.json()
print("Task ID:", data["task_id"])
print("Result:", data["result"])
```

### 异步（提交+轮询）示例
```python
import requests
import time

payload = {
    "prompt": "把这件衣服变成长款",
    "image_urls": [
        "https://huayiyi-ai.oss-cn-shanghai.aliyuncs.com/test_tmp/1759....png"
    ],
}

submit = requests.post(
    "http://127.0.0.1:8000/tasks/nanobanana-image",
    json=payload,
    timeout=10,
)
submit.raise_for_status()
task_id = submit.json()["task_id"]
print("Task queued:", task_id)

while True:
    time.sleep(2)
    status = requests.get(f"http://127.0.0.1:8000/tasks/{task_id}", timeout=10)
    if status.status_code == 404:
        raise RuntimeError("task not found")
    info = status.json()
    print("status:", info["status"])
    if info["status"] in {"completed", "failed"}:
        print("result:", info.get("result"))
        break
```

## 日志与监控

框架默认输出结构化日志，可在 `config.py` 中修改日志等级或接入自定义 Sink。心跳记录会保存在 Redis 的 `heartbeat:*` key 下，可以结合监控任务实现故障自愈。

