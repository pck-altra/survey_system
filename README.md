# Survey System — 在线问卷系统

> 华东师范大学「当代数据管理系统」课程项目  
> 技术栈：FastAPI + MongoDB 后端 + 原生 HTML/JS 前端  
> 本分支（`main`）为**两阶段合并版**，用于总览与索引；分阶段代码请见 `stage1` / `stage2` 分支。

---

## 1. 分支说明

| 分支 | 内容 | 对应提交 |
| --- | --- | --- |
| `stage1` | **第一阶段**：在线问卷系统 v1.0（用户 / 问卷 / 题目 / 填写 / 统计） | `7ecd9d8` |
| `stage2` | **第二阶段**：新增题库 / 可复用题目（需求变更 v2.0），包含第一阶段全部内容 | `c2fd587` |
| `main` | 两阶段合并版 + 本 README（说明两阶段文件位置） | — |

> `stage2` 是在 `stage1` 基础上**增量**开发的，因此 `stage2` 分支本身就包含第一阶段的全部文件。
> 想看纯第一阶段的代码，请切到 `stage1` 分支。

```bash
git clone https://github.com/pck-altra/survey_system.git
cd survey_system

git checkout stage1   # 第一阶段
git checkout stage2   # 第二阶段
git checkout main     # 两阶段合并版（默认）
```

---

## 2. 两阶段文件位置

### 2.1 第一阶段文件（`stage1` 分支独有，后续阶段未改动或仅微调）

#### 后端 `app/`

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `app/main.py` | 45 | FastAPI 入口，挂载全部路由 |
| `app/config.py` | 35 | 配置（MongoDB URI、库名、bcrypt 代价等） |
| `app/db.py` | 125 | MongoDB 连接管理 + 索引创建 |
| `app/routing.py` | 134 | 条件跳转路由引擎 |
| `app/validation.py` | 180 | 答案校验逻辑 |
| `app/api/auth.py` | 63 | 注册 / 登录（JWT） |
| `app/api/deps.py` | 104 | 依赖注入（当前用户、DB 会话） |
| `app/api/surveys.py` | 195 | 问卷 CRUD、发布、关闭 |
| `app/api/questions.py` | 161 | 题目增删改 |
| `app/api/responses.py` | 175 | 填写流程（开始 / 答题 / 完成） |
| `app/api/statistics.py` | 111 | 统计接口 |
| `app/api/schemas.py` | 182 | Pydantic 请求 / 响应模型 |
| `app/models/users.py` | 109 | 用户 Repository |
| `app/models/surveys.py` | 202 | 问卷 Repository |
| `app/models/questions.py` | 338 | 题目 Repository（含 `next_rule` 校验） |
| `app/models/responses.py` | 169 | 回答路径 Repository |
| `app/models/answers.py` | 223 | 答案 Repository |
| `app/scripts/seed.py` | 146 | 种子数据脚本 |
| `app/scripts/ensure_indexes.py` | 30 | 索引创建脚本 |

#### 前端 `frontend/`

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `frontend/index.html` | 242 | 管理端页面（登录 / 注册 / 创建问卷 / 填卷 / 统计） |
| `frontend/app.js` | 1038 | 问卷与填写流程全部逻辑 |
| `frontend/fill.html` | 288 | 分享出去的填写页（`?token=xxx`） |
| `frontend/styles.css` | 438 | 样式 |

#### 测试 `tests/`（第一阶段 109 条）

| 文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| `tests/conftest.py` | — | 夹具（内存 Mongo / 客户端 / 用户） |
| `tests/test_users.py` | 9 | 注册、登录、重复用户名、密码校验 |
| `tests/test_surveys.py` | 12 | 问卷 CRUD、发布、关闭、权限 |
| `tests/test_questions.py` | 13 | 题目增删改、题型、选项 |
| `tests/test_responses.py` | 10 | 填写流程、提交校验 |
| `tests/test_statistics.py` | 5 | 统计聚合 |
| `tests/test_routing.py` | 15 | 条件跳转引擎 |
| `tests/test_validation.py` | 22 | 答案校验规则 |
| `tests/test_api.py` | 23 | 接口级集成、鉴权、健康检查 |

#### 文档 `docs/`

| 文件 | 说明 |
| --- | --- |
| `docs/项目完成报告.md` | **第一阶段**完整项目报告（9 个章节） |
| `docs/数据库设计.md` | MongoDB 集合设计、索引、关键查询（v1） |
| `docs/测试用例.md` | 第一阶段 17 条手工 + API 用例清单 |
| `docs/大作业一第一阶段.docx` | 原始需求文档 |
| `docs/AI使用过程.md` | AI 协作日志（第一阶段部分） |

### 2.2 第二阶段新增文件（仅存在于 `stage2` / `main` 分支）

#### 后端

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `app/api/bank.py` | 457 | **新增** 题库 API：题目 CRUD、版本、共享、使用情况、跨问卷统计 |
| `app/models/bank.py` | 532 | **新增** 题库 Repository（版本家族 `root_id` / `parent_id` 链） |

#### 前端

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `frontend/bank.js` | 609 | **新增** 题库模块全部逻辑（列表 / 版本 / 共享 / 统计 / 选题） |

#### 测试

| 文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| `tests/test_bank.py` | 27 | 题库 8 个测试类：保存复用题、共享、修改隔离、版本化、使用情况、题库、跨问卷统计 |
| `tests/e2e/conftest.py` | — | **新增** E2E 夹具：真拉起 uvicorn 子进程 + 独立临时库 + HTTP 驱动 |

#### 文档

| 文件 | 说明 |
| --- | --- |
| `docs/项目完成报告（第二阶段）.md` | **第二阶段**（题库 / 可复用题目）项目报告 |
| `docs/大作业一：需求变更.docx` | 第二阶段需求变更文档（v2.0） |
| `docs/2026_ECNU_PJ1_2_潘淳恺.pdf` | 需求变更扫描件 |

### 2.3 第二阶段改动的既有文件

| 文件 | 改动内容 |
| --- | --- |
| `app/api/questions.py` | 新增「从题库选题」入参（`bank_question_id`）与 `bank_ref` 溯源字段 |
| `app/api/schemas.py` | 新增题库相关的 Pydantic 模型（`BankQuestionOut` / `BankHistoryOut` / `BankUsageOut` / `BankStatsOut` 等） |
| `app/models/questions.py` | 题目文档新增 `bank_ref` 字段 |
| `app/models/answers.py` | 新增按 `bank_ref.root_id` 聚合的跨问卷统计查询 |
| `app/models/__init__.py` | 导出 `BankQuestionRepo` |
| `app/db.py` | `bank_questions` 集合索引 |
| `app/main.py` | 注册 `/api/bank` 路由 |
| `frontend/index.html` | 顶部导航「题库」入口、题库相关弹窗、问卷编辑器「📚 从题库选择」 |
| `frontend/app.js` | 问卷编辑器接入题库选题 / 来源版本切换 |
| `frontend/styles.css` | 题库模块样式 |
| `tests/conftest.py` | 题库相关夹具 |
| `tests/test_api.py` | 题库接口集成用例 |

---

## 3. 快速启动

### 3.1 启动 MongoDB

```bash
# macOS（官方安装包）
mongod --dbpath /usr/local/var/mongodb --logpath /usr/local/var/log/mongodb/mongo.log --fork

# 或 Homebrew 安装（tap mongo-community）
brew services start mongodb-community
```

### 3.2 安装依赖

```bash
pip install -r requirements.txt
```

### 3.3 启动后端（项目根目录）

```bash
uvicorn app.main:app --reload --port 8000
```

- API 文档：http://localhost:8000/docs
- API 根路径：http://localhost:8000/api/...

### 3.4 启动前端（另一个终端）

```bash
cd frontend
python3 -m http.server 8080
```

然后访问 **http://localhost:8080**，登录后点顶部「题库」标签进入第二阶段模块。

> 前端为纯静态文件，无需构建。`frontend/app.js` 第 6 行的 `API_BASE` 指向 `http://localhost:8000/api`，改后端端口时改这一行即可。

---

## 4. 项目结构（`main` / `stage2` 分支）

```
survey_system/
├── app/
│   ├── main.py            # FastAPI 入口，挂载所有路由
│   ├── config.py          # 配置（MongoDB URI、数据库名等）
│   ├── db.py              # MongoDB 连接管理 + 索引创建
│   ├── routing.py         # 条件跳转路由引擎
│   ├── validation.py      # 答案校验逻辑
│   ├── api/
│   │   ├── auth.py        # 注册 / 登录
│   │   ├── surveys.py     # 问卷 CRUD
│   │   ├── questions.py   # 题目增删改（支持从题库选题）
│   │   ├── responses.py   # 填写流程（提交答案、推进下一题）
│   │   ├── statistics.py  # 统计接口
│   │   ├── bank.py        # 题库 / 版本 / 共享 / 使用情况 / 跨问卷统计  ← 第二阶段
│   │   └── schemas.py     # Pydantic 请求/响应模型
│   └── models/
│       ├── users.py       # 用户 Repository
│       ├── surveys.py     # 问卷 Repository
│       ├── questions.py   # 题目 Repository（含 next_rule 校验、bank_ref）
│       ├── responses.py   # 回答路径 Repository
│       ├── answers.py     # 答案 Repository（含跨问卷统计）
│       └── bank.py        # 题库题目 Repository（版本家族）              ← 第二阶段
├── frontend/
│   ├── index.html         # 管理端页面（登录/注册/创建问卷/填卷/统计/题库）
│   ├── app.js             # 问卷与填写流程相关逻辑
│   ├── bank.js            # 题库模块逻辑                                  ← 第二阶段
│   ├── fill.html          # 分享出去的填写页
│   └── styles.css         # 样式
├── tests/                 # pytest 自动测试（10 个模块，136 条用例）
│   └── e2e/               # 端到端夹具（真 uvicorn + 独立临时库）          ← 第二阶段
├── docs/
│   ├── 数据库设计.md              # 完整设计文档（v2，含题库）
│   ├── 测试用例.md                # 第一阶段手工 + 第二阶段自动化
│   ├── 项目完成报告.md            # 第一阶段报告
│   ├── 项目完成报告（第二阶段）.md  # 第二阶段报告                        ← 第二阶段
│   └── AI使用过程.md              # AI 协作日志
└── requirements.txt
```

---

## 5. 核心概念：题库与版本（第二阶段）

`bank_questions` 集合中**一个文档 = 一个题目版本**：

- `root_id` 标识「题目家族」（同一道题的所有版本）
- `parent_id` 记录「这个版本从哪个版本改过来」（版本链 v1 → v2 → v3）
- 修改题目 = 插入新版本文档，旧版本原封不动

从题库选题时，问卷里存的是**内容快照** + 一个溯源字段 `bank_ref`：

```text
题库 v2 ──复制快照──→ 问卷 A 的题目（内容定格在 v2）
                        bank_ref → { root_id, version_id }
```

因此：

| 行为 | 结果 |
|------|------|
| 题库题目改成 v3 | 问卷 A 里的题目**不变**（仍是 v2 的内容） |
| 问卷 B 选用 v3 | 只有问卷 B 变，A 不受影响 |
| 查看「这题被哪些问卷用了」 | 按 `bank_ref.root_id` 反查问卷列表 |
| 查看「这题在所有问卷里的分布」 | 按 `bank_ref.root_id` 聚合所有 `answers` |

---

## 6. 核心概念：条件跳转（next_rule，第一阶段）

| 模式 | 说明 |
|------|------|
| `mode: "default", fallback: "next"` | 默认下一题（顺序答题） |
| `mode: "default", fallback: "end"` | 结束问卷 |
| `mode: "by_option", fallback: "next", branches: [{when, goto}]` | 按选项跳转 |

使用：题目选为单选 / 多选并填好选项 → 「答题后跳转」设为**按选项跳转** → 为每个选项填目标题号（从 1 开始）→ 留空则走 `fallback`。

---

## 7. 测试

```bash
pytest -q                        # 全量（136 条）
pytest tests/test_bank.py -v     # 仅第二阶段题库用例（27 条）
```

---

## 8. 环境变量（可选）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SURVEY_MONGO_URI` | `mongodb://127.0.0.1:27017` | MongoDB 连接地址 |
| `SURVEY_MONGO_DB` | `survey_system` | 数据库名 |
| `SURVEY_BCRYPT_COST` | `12` | 密码哈希强度 |
| `SURVEY_TOKEN_LEN` | `7` | 问卷 Token 长度 |
| `SURVEY_MONGO_TIMEOUT_MS` | `5000` | MongoDB 超时（毫秒） |

---

## 9. 常见问题

### Q: 启动报错 `pymongo.errors.ServerSelectionTimeoutError`

MongoDB 未启动，按 §3.1 启动即可。

### Q: 启动报错 `ModuleNotFoundError: No module named 'app'`

在项目**根目录**执行 `uvicorn`。

### Q: 问卷填写页面打不开 / Token 不生效

双击打开 `index.html` 时 URL 参数 `?token=xxx` 会被忽略，请用 `python3 -m http.server` 方式访问。

### Q: 想重置数据库

```js
// mongo shell
use survey_system
db.dropDatabase()
```

---

## 10. 交付物清单

| 文件 / 目录 | 说明 |
|------------|------|
| `app/` | 后端全部代码（FastAPI 应用、路由、Repository、数据引擎、题库） |
| `frontend/` | 前端全部代码（HTML + CSS + JS，含题库模块） |
| `requirements.txt` | Python 依赖清单 |
| `tests/` | pytest 自动测试（10 个模块，136 条用例 + E2E 夹具） |
| `docs/项目完成报告.md` | 第一阶段完整项目报告 |
| `docs/项目完成报告（第二阶段）.md` | 第二阶段（题库 / 可复用题目）项目报告 |
| `docs/数据库设计.md` | MongoDB 集合设计、索引、关键查询示例（v2） |
| `docs/测试用例.md` | 第一阶段 17 条手工 + API 用例、第二阶段 27 条自动化用例 |
| `docs/AI使用过程.md` | AI 协作日志，含 AI 做错 / 改对 / 设计的对账记录 |
