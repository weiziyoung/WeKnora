# submit_task.py 脚本说明文档

## 脚本目的
负责消费 `document_status_table` 中状态为 `discover` 的文件，将其提交到 RAG 系统的指定知识库中。提交成功后，更新数据库状态为 `pending` 或 RAG 系统返回的初始状态，并回填 `knowledge_id`。

## 核心配置
*   **Knowledge Base ID**: 启动时通过环境变量或参数指定目标知识库 ID。
*   **API 地址**: `POST /api/v1/knowledge-bases/{id}/knowledge/file`

## 处理流程
1.  **获取任务**:
    *   从 SQLite 数据库查询状态为 `discover` 的记录。
    *   每次批量获取一定数量（如 10-50 条），避免内存占用过大。
2.  **提交文件**:
    *   遍历获取到的记录。
    *   读取文件内容。
    *   调用 RAG 系统上传接口。
        *   参数 `file`: 文件流
        *   参数 `fileName`: 文件名
        *   参数 `enable_multimodel`: 默认为 `False` (后续可配置)
3.  **状态更新**:
    *   **成功**:
        *   获取 API 返回的 `knowledge_id` 和初始状态（通常是 `pending` 或 `processing`）。
        *   更新数据库记录：
            *   `file_status` -> API 返回的状态 (如 `pending`)
            *   `knowledge_id` -> API 返回的 ID
            *   `process_at` -> 当前时间
            *   `failed_msg` -> 清空
    *   **失败**:
        *   更新数据库记录：
            *   `file_status` -> `failed`
            *   `failed_msg` -> 记录具体的 API 错误信息或网络异常
            *   **注意**: 暂时不进行自动重试，留给开发人员人工排查错误原因。
4.  **异常处理**:
    *   捕获文件读取错误（如文件被占用、权限不足）。
    *   捕获网络请求超时或连接错误。

## 数据库更新
*   主要操作 `document_status_table` 表。
*   同时记录脚本执行统计到 `script_process_record` 表。

---

# polling_task.py 脚本说明文档

## 脚本目的
轮询数据库中处于“进行中”状态的任务，调用 RAG 系统查询接口获取最新状态，并同步更新到数据库。

## 核心配置
*   **轮询目标状态**: `pending`, `processing`
*   **API 地址**: `GET /api/v1/knowledge/{id}`

## 处理流程
1.  **获取任务**:
    *   从 SQLite 数据库查询状态为 `pending` 或 `processing` 的记录。
    *   **必须**确保 `knowledge_id` 不为空。
2.  **状态查询**:
    *   遍历任务列表。
    *   调用查询接口获取最新状态 (`parse_status`)。
3.  **状态同步**:
    *   **状态变化**:
        *   如果 API 返回的状态与数据库中不同，则更新数据库。
    *   **终态处理**:
        *   `completed`: 更新 `finish_at` = 当前时间，`file_status` = `completed`。
        *   `failed`: 更新 `finish_at` = 当前时间，`file_status` = `failed`，并记录 `error_message` 到 `failed_msg`。
    *   **中间状态**:
        *   `pending`, `processing`: 保持不变或仅更新最后检查时间（如果有该字段）。
4.  **异常处理**:
    *   若查询接口返回 404（知识 ID 不存在），说明 RAG 端数据丢失或已被删除。
        *   策略：标记为 `failed`，错误信息为 "Knowledge ID not found in RAG system"。
    *   若查询接口超时或 500，跳过本次更新，等待下一次轮询。

## 数据库更新
*   主要操作 `document_status_table` 表。
*   同时记录脚本执行统计到 `script_process_record` 表。
