# Docker 迁移安装清单

这份清单用于把当前项目的 Docker 服务搬到另一台电脑重新安装。

## 当前 Docker 服务

项目里有两套 Compose 配置：

1. `01_data_collection_workflow/docker-compose.yml`
   - 服务：n8n
   - 镜像：`docker.n8n.io/n8nio/n8n:latest`
   - 端口：`5678`
   - 数据目录：`D:/py/n8n`
   - n8n 附加数据目录：`D:/py/n8ndata`

2. `02_milvus_knowledge_base/docker-compose.yml`
   - 服务：Milvus standalone、etcd、MinIO、Attu
   - 镜像：
     - `quay.io/coreos/etcd:v3.5.18`
     - `minio/minio:RELEASE.2024-12-18T13-15-44Z`
     - `milvusdb/milvus:v2.6.0`
     - `zilliz/attu:v2.6`
   - 端口：
     - Milvus：`19530`
     - Milvus health：`9091`
     - MinIO：`9000`
     - MinIO Console：`9001`
     - Attu：`8000`
   - 数据目录：`02_milvus_knowledge_base/volumes`

## 需要拷贝的文件和目录

如果只想在新电脑装一个空环境，拷贝这些文件即可：

- `01_data_collection_workflow/docker-compose.yml`
- `01_data_collection_workflow/.env.example`
- `02_milvus_knowledge_base/docker-compose.yml`

如果要把当前数据也一起搬过去，还要拷贝：

- `D:/py/n8n`
- `D:/py/n8ndata`
- `02_milvus_knowledge_base/volumes`

如果还要继续运行 Python 脚本和 MCP 服务，也要带上对应 `.env` 文件：

- `02_milvus_knowledge_base/.env`
- `03_mcp_search_server/.env`

注意：这些 `.env` 文件里有 API Key。换电脑前建议重新生成密钥，或至少不要把它们发给别人。

## 推荐迁移步骤

### 1. 在旧电脑停止服务

在拷贝数据目录之前，先停止容器，避免 SQLite、Milvus、MinIO 数据复制不完整。

```powershell
cd F:\py\milvus-mcp-rag-agent\01_data_collection_workflow
docker compose down

cd F:\py\milvus-mcp-rag-agent\02_milvus_knowledge_base
docker compose down
```

### 2. 拷贝项目和数据

把项目目录拷到新电脑，例如：

```text
F:\py\milvus-mcp-rag-agent
```

如果要保留 n8n 工作流、账号、凭据和生成数据，也把下面两个目录拷到新电脑：

```text
D:\py\n8n
D:\py\n8ndata
```

Milvus 数据在项目内：

```text
F:\py\milvus-mcp-rag-agent\02_milvus_knowledge_base\volumes
```

### 3. 新电脑配置 n8n 路径

如果新电脑仍使用 `D:/py/n8n` 和 `D:/py/n8ndata`，可以不改。

如果路径不同，在 `01_data_collection_workflow` 目录下复制一份 `.env.example`，命名为 `.env`，然后修改：

```env
N8N_IMAGE=docker.n8n.io/n8nio/n8n:latest
N8N_DATA_DIR=D:/py/n8n
N8N_EXTRA_DATA_DIR=D:/py/n8ndata
```

### 4. 启动服务

先启动 Milvus：

```powershell
cd F:\py\milvus-mcp-rag-agent\02_milvus_knowledge_base
docker compose up -d
```

再启动 n8n：

```powershell
cd F:\py\milvus-mcp-rag-agent\01_data_collection_workflow
docker compose up -d
```

### 5. 验证访问

- n8n：http://localhost:5678
- Attu：http://localhost:8000
- Milvus：http://localhost:19530
- MinIO Console：http://localhost:9001

## 常见注意事项

- 新电脑需要先安装 Docker Desktop，并确保 Docker 已启动。
- 如果端口 `5678`、`8000`、`9000`、`9001`、`19530`、`9091` 被占用，需要改 compose 里的宿主机端口。
- `02_milvus_knowledge_base/docker-compose.yml` 里的 Milvus 数据卷是相对路径，项目目录整体复制过去即可。
- n8n 默认使用 SQLite，迁移时一定要停容器后再复制 `D:/py/n8n`，否则可能丢失最新数据。
- 如果新电脑运行 Python 脚本，检查 `02_milvus_knowledge_base/.env` 里的 `JSON_DATA_PATH` 是否还是有效路径。
