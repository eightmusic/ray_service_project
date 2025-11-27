# Ray Service 项目框架

该项目提供一个基于 **Ray Serve** 的算法服务框架，具备以下能力：

- 统一的模型入口：通过模型名路由到本地模型或外部 API。
- 使用 Redis 追踪任务消息、并支持心跳检测。
- 按模型维度控制并发与资源（GPU）配置。
- 框架化代码，便于快速接入新的算法。

## 快速开始

### 本地运行

1. 安装依赖（Python 3.10+）：

   ```bash
   pip install --upgrade pip
   pip install poetry
   poetry install
   ```

2. 准备 Redis（如无可用实例，可临时拉取）：

   ```bash
   docker run -p 6379:6379 redis:7
   ```

3. 配置环境变量：

   ```bash
   cp .env.example .env
   # 根据需要修改 REDIS_URL、NANOBANANA_API_KEY 等
   ```

4. 启动 Ray Serve：

   ```bash
   poetry run python -m ray_service.run
   ```

5. 访问接口（同步）：

   ```bash
   curl -X POST "http://127.0.0.1:8000/invoke/local-echo" \
     -H "Content-Type: application/json" \
     -d '{"text": "hello"}'
   ```

   异步模式：

   ```bash
   curl -X POST "http://127.0.0.1:8000/tasks/local-echo" \
     -H "Content-Type: application/json" \
     -d '{"text": "hello"}'
   curl "http://127.0.0.1:8000/tasks/<task_id>"
   ```

### Docker Compose 部署

1. 复制环境变量并设置 Docker 专用的 Redis 地址：

   ```bash
   cp .env.example .env
   # REDIS_URL 可留空，compose 默认使用 redis://ray-service-redis:6379/0
   export NANOBANANA_API_KEY=实际密钥
   ```

2. 构建并启动：

   ```bash
   docker compose up --build
   ```

   - `ray-service-app`：Ray Serve + FastAPI 应用，默认监听 `8000`。
   - `ray-service-redis`：Redis 7，暴露 `6379`，数据持久化到 `redis-data` volume。

3. 验证：

   ```bash
   curl http://127.0.0.1:8000/healthz
   ```

4. 停止服务：

   ```bash
   docker compose down
   # 如需清理 volume：docker compose down -v
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

### 环境变量说明

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `REDIS_URL` | 任务/心跳存储地址 | `redis://localhost:6379/0` |
| `SERVICE_HOST` / `SERVICE_PORT` | Ray Serve HTTP 监听地址 | `0.0.0.0` / `8000` |
| `HEARTBEAT_INTERVAL_SECONDS` / `HEARTBEAT_TTL_SECONDS` | 心跳频率与 TTL | `10` / `30` |
| `DEFAULT_MAX_CONCURRENCY` | 未指定模型并发时的默认值 | `4` |
| `NANOBANANA_API_KEY` | NanoBanana 示例模型所需密钥 | 空 |
| `LOG_LEVEL` | 日志等级 | `INFO` |

> `Settings`（`config.py`）会自动读取 `.env` 或环境变量，`get_settings()` 在应用生命周期中复用同一个配置实例。

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

### 如果你要使用外部（云端或自建）Redis，可以这么做：
1. 删除或注释掉 compose 里的 redis 服务，同时去掉 depends_on: - redis。
2. 在 .env 或运行 compose 时设置 REDIS_URL 指向外部 Redis，例如：
```yml
environment:
  REDIS_URL: redis://default:<password>@your-redis-host:6379/0
```
compose 中的 environment 会读取这个值。
3. 删除或者注释ray-service:下的    
    depends_on:
      - redis
4. 然后运行 docker compose up --build，只会启动 ray-service 容器，它会直接连接外部 Redis。

--build 只是告诉 Compose 在启动前重新构建镜像，它不会决定启动哪些服务。默认情况下，docker compose up 会启动 docker-compose.yml 中定义的所有服务（这里只有 redis 和 ray-service），无论有没有 --build。所以：
docker compose up --build：先构建 ray-service 镜像，再启动 redis 和 ray-service。
docker compose up（无 --build）：直接启动两个服务，使用已有镜像；如果镜像不存在，会自动构建一次。
如果想只启动 ray-service，可以指定服务名：docker compose up --build ray-service，这时 redis 不会启动（除非 depends_on 要求）。不过通常两个服务都要一起启动。

## 日志与监控

框架默认将日志输出到标准输出（`logging.basicConfig`），Compose / 进程管理器可统一采集。若需写入文件，可在 `logging_setup.configure_logging` 中添加自定义 Handler。

- 心跳键：`ray_service:heartbeat:<worker_id>`，可用于探活。
- 任务 Hash：`ray_service:task:<task_id>`，包含 payload、状态、结果，可由外部可视化工具订阅。
- 任务 Stream：`ray_service:tasks`，记录提交历史，可用于审计或重放。

