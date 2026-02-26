# discover_files.py 脚本说明文档

## 脚本目的
本脚本旨在将 Windows Server 上 ERP 系统中所有支持的 RAG（Retrieval-Augmented Generation）文档提取出来，并将其状态同步到 SQLite 数据库中。

核心功能包括：
1.  **文件发现**：遍历指定目录，识别支持的文件类型，将其元数据存入数据库，状态置为 `discover`。
2.  **文件更新**：监控文件变化（修改时间或大小），若发生更新，则调用 API 删除 RAG 系统中的旧文件，并将数据库记录重置为 `discover` 状态，等待后续重新处理。
3.  **文件删除**：若文件在磁盘上被删除，脚本会自动识别，调用 API 删除 RAG 系统中的对应知识，并将数据库记录标记为 `deleted`。

## 支持的文件类型
脚本目前支持扫描以下类型的文件：
*   **文档**: PDF (`.pdf`), Word (`.doc`, `.docx`), Markdown (`.md`, `.markdown`), Text (`.txt`)
*   **表格**: Excel (`.xlsx`, `.xls`), CSV (`.csv`)
*   **图片**: JPG (`.jpg`, `.jpeg`), PNG (`.png`), GIF (`.gif`)

## 扫描目录配置
脚本采用“前缀 + 中缀列表 + 后缀”的方式拼接扫描路径。

*   **前缀**: `D:\Zbintel\`
*   **后缀**: `\SYSA\Edit\upimages`
*   **中缀列表**:
    *   `ZBIntel_jhxny_hf_8088`
    *   `ZBintel_lbjs_tc_9199`
    *   `ZBIntel_LBTC_XT1_1011`
    *   `ZBIntel_LBTC_XT2_2022`
    *   `ZBIntel_LBTC_XT3_3033`
    *   `ZBIntel_LBZN_TG_4044`
    *   `ZBIntel_weiyy_tg_9099`
    *   `ZBIntel_YYJ_SC_5055`
    *   `ZBIntel_yyjs1_6066`
    *   `ZBIntel_yyjs2_7077`

## 数据库设计 (SQLite)

### 1. `document_status_table` (文档状态表)
记录每个文件的处理状态和元数据。

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | INTEGER | 主键 |
| `filename` | TEXT | 文件名 (包含扩展名) |
| `filepath` | TEXT | 文件完整路径 (唯一索引) |
| `file_status` | TEXT | 文件状态: `discover` -> `pending` -> `processing` -> `completed` -> `deleted` |
| `created_at` | DATETIME | 文件被发现或重新置为 discover 的时间 |
| `last_modified_time` | REAL | 文件最后修改时间戳 (用于快速比对) |
| `process_at` | DATETIME | 开始处理的时间 |
| `finish_at` | DATETIME | 处理完成或标记删除的时间 |
| `failed_msg` | TEXT | 处理失败时的错误消息 |
| `file_size` | INTEGER | 文件大小 (字节) |
| `file_hash` | TEXT | 文件内容的 SHA256 哈希值 |
| `file_store_path` | TEXT | 文件在存储系统中的路径 |
| `knowledge_id` | TEXT | 对应 RAG 系统中的知识 ID (初始为空，后续生成) |

### 2. `script_process_record` (脚本执行记录表)
记录脚本每次运行的统计信息。

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | INTEGER | 主键 |
| `script_name` | TEXT | 脚本名称 (`discover_files.py`) |
| `process_duration` | REAL | 脚本执行耗时 (秒) |
| `process_count` | INTEGER | 处理总数 (新增 + 更新 + 删除) |
| `insert_count` | INTEGER | 新增文件数 |
| `update_count` | INTEGER | 更新文件数 |
| `delete_count` | INTEGER | 删除文件数 |
| `process_timestamp` | DATETIME | 执行时间 |
| `status` | TEXT | 执行状态 (`success` / `fail`) |
| `failed_reason` | TEXT | 失败原因 |

## 处理流程逻辑

### 1. 初始化与扫描
*   连接 SQLite 数据库，启用 **WAL (Write-Ahead Logging)** 模式以提高并发读写性能。
*   从数据库加载所有非 `deleted` 状态的文件记录 (`db_files`)。
*   遍历磁盘目录，收集当前存在的所有文件及其元数据 (`current_files`)。
*   过滤掉不支持的扩展名和小于 1KB 的文件。

### 2. 新增处理 (Insert)
*   **条件**: 文件在磁盘上存在 (`current_files`)，但不在数据库中 (`db_files`)。
*   **操作**:
    1.  插入新记录，状态设为 `discover`。
    2.  记录 `created_at`, `last_modified_time`, `file_size`。
    3.  `file_hash` 暂设为 `NULL` (由后续 submit 脚本回填)。

### 3. 更新处理 (Update)
*   **条件**: 文件在磁盘和数据库中都存在。
*   **竞争保护**: 如果文件状态为 `processing`，**跳过本次更新**，防止与消费者程序发生状态竞争。
*   **变更检测**:
    1.  比对元数据: `mtime` (修改时间) 或 `file_size` (大小) 是否变化。
*   **操作**:
    1.  若确认元数据变化，且数据库中存在 `knowledge_id`，调用 API 删除 RAG 系统中的旧知识。
    2.  更新数据库记录：
        *   `file_status` -> `discover`
        *   `knowledge_id` -> `NULL`
        *   `file_hash` -> `NULL`
        *   更新 `created_at`, `last_modified_time`, `file_size`。

### 4. 删除处理 (Delete)
*   **条件**: 文件在数据库中存在 (`db_files`)，但在磁盘上已消失 (`current_files`)。
*   **操作**:
    1.  若数据库中存在 `knowledge_id`，调用 API 删除 RAG 系统中的对应知识。
    2.  更新数据库记录：
        *   `file_status` -> `deleted`
        *   `finish_at` -> 当前时间

## 依赖与环境
*   **Python 版本**: 3.6+
*   **第三方库**: `requests`
    ```bash
    pip install requests
    ```
*   **环境变量**:
    *   `WEKNORA_API_URL`: RAG 系统的 API 地址 (默认: `http://localhost:8000`)

## API 接口调用
脚本使用以下接口清理旧知识：
*   **接口**: `DELETE /api/v1/knowledge/{id}`
*   **逻辑**: 同步接口，调用成功即视为物理删除。若返回 404 也视为删除成功。
