# Survey System — 在线问卷系统

> 华东师范大学「当代数据管理系统」课程项目  
> 技术栈：FastAPI + MongoDB 后端 + 原生 HTML/JS 前端

---

## 项目概览

本项目实现了一个完整的在线问卷系统，包含以下功能：

| 模块 | 说明 |
|------|------|
| **用户系统** | 注册 / 登录（JWT 认证） |
| **问卷管理** | 创建、编辑、发布、关闭、删除问卷 |
| **题型支持** | 单选题、多选题、文本题、数字题 |
| **条件跳转** | 支持按选项跳转到指定题号（按选项跳转） |
| **匿名填写** | 问卷可配置是否允许匿名提交 |
| **统计展示** | 柱状图、饼图、均值/范围统计 |
| **Token 分发** | 发布后生成唯一 Token，可通过链接分享问卷 |
| **题库（第二阶段）** | 保存常用题目、共享给别人、版本化（改题不影响旧问卷）、查看使用情况与跨问卷统计 |

### 技术架构

```
前端（静态）        后端（FastAPI）
┌──────────────┐    ┌─────────────────────────────┐
│ index.html   │    │  /api/auth   用户认证       │
│ app.js       │◄──►│  /api/surveys 问卷 CRUD    │
│ bank.js      │    │  /api/questions 题目管理     │
│ styles.css   │    │  /api/responses 填写流程   │
└──────────────┘    │  /api/statistics 统计     │
                    │  /api/bank  题库 / 版本   │
                    └──────────┬────────────────┘
                               │
                    ┌──────────▼────────────────┐
                    │      MongoDB              │
                    │  users / surveys /        │
                    │  questions / responses /  │
                    │  answers / bank_questions │
                    └───────────────────────────┘
```

---

## 环境要求

- **Python** ≥ 3.10
- **MongoDB** ≥ 6.0（本地运行）
- **Node.js**（可选，仅前端开发不需要）

---

## 快速启动

### 1. 启动 MongoDB

```bash
# macOS（使用 Homebrew）
brew services start mongodb-community

# 或手动启动
mongod --dbpath /usr/local/var/mongodb
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动后端

```bash
uvicorn app.main:app --reload --port 8000
```

后端运行在 `http://localhost:8000`，可访问：
- API 文档：`http://localhost:8000/docs`（Swagger UI）
- API 根路径：`http://localhost:8000/api/...`

### 4. 启动前端

前端为纯静态文件，有以下两种方式：

#### 方式一：直接在浏览器打开（无需服务器）

双击打开 `frontend/index.html` 文件即可使用。

> 注意：直接打开文件时，`fill.html` 分享链接中的 URL 参数无法正常工作。若需要测试问卷填写流程，请使用方式二或方式三。

#### 方式二：用 Python 内置 HTTP 服务器

```bash
cd frontend
python3 -m http.server 8080
```

然后访问 `http://localhost:8080`

#### 方式三：让 uvicorn 同时托管前端（推荐）

修改 `app/main.py` 让它把 `frontend/` 目录挂载到根路径，之后只跑后端即可。

在 `app/main.py` 顶部添加导入：
```python
from fastapi.staticfiles import StaticFiles
```

在 `app.include_router(...)` 之后添加：
```python
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
```

启动后端：
```bash
uvicorn app.main:app --reload --port 8000 --app-dir .
```

然后访问 `http://localhost:8000`。CORS 已全开，`?token=xxx` URL 参数正常工作。

---

## 前端调试

### Chrome / Edge 开发者工具

1. 按 **F12** 打开开发者工具
2. 切换到 **Sources** 面板可断点调试 `app.js`
3. 切换到 **Network** 面板可查看所有 API 请求（请求体、响应体、状态码）
4. 切换到 **Console** 面板可查看 `console.log` 输出和 JavaScript 错误

### 修改代码后即时生效

前端为纯静态文件，无需构建：
- 修改 `frontend/app.js` 或 `frontend/styles.css` 后，**直接刷新浏览器页面**（Cmd+R / Ctrl+R）即可看到变化
- 若后端正在用 `uvicorn --reload` 运行，修改后端 Python 文件也会自动重载

### API 请求调试

`app.js` 中的 `api()` 函数封装了所有请求，默认在控制台不打印日志。如需调试，可在 `app.js` 开头添加：

```js
// 在 api() 函数开头添加一行：
async function api(path, options = {}) {
  console.log('[API]', path, options);
  // ...
```

### 修改 API 地址

`app.js` 第 7 行定义了 API 基础地址：

```js
const API_BASE = 'http://localhost:8000/api';
```

若后端端口不是 8000，修改此处即可。

### 清除登录状态

前端将用户 Token 存在 `localStorage`，调试时可：

1. 打开浏览器控制台（F12 → Console）
2. 执行 `localStorage.clear()` 清除所有本地存储

或直接在浏览器地址栏执行：
```js
javascript:localStorage.clear();location.reload();
```

---

## 项目结构

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
│   │   ├── bank.py        # 题库 / 版本 / 共享 / 使用情况 / 跨问卷统计
│   │   └── schemas.py     # Pydantic 请求/响应模型
│   └── models/
│       ├── users.py       # 用户 Repository
│       ├── surveys.py     # 问卷 Repository
│       ├── questions.py   # 题目 Repository（含 next_rule 校验）
│       ├── responses.py   # 回答路径 Repository
│       ├── answers.py     # 答案 Repository（含跨问卷统计）
│       └── bank.py        # 题库题目 Repository（版本家族）
├── frontend/
│   ├── index.html         # 管理端页面（登录/注册/创建问卷/填卷/统计/题库）
│   ├── app.js             # 问卷与填写流程相关逻辑
│   ├── bank.js            # 题库模块逻辑（列表/版本/共享/统计/选题）
│   └── styles.css         # 样式
├── tests/                 # pytest 自动测试（9 个模块，136 条用例）
├── docs/
│   ├── 数据库设计.md       # 完整设计文档（v2，含题库）
│   ├── 测试用例.md         # 用例文档（v2，第一阶段手工 + 第二阶段自动化）
│   ├── 项目完成报告.md     # 第一阶段报告
│   ├── 项目完成报告（第二阶段）.md  # 第二阶段（题库）报告
│   └── AI使用过程.md      # AI 协作日志
└── requirements.txt
```

---

## 核心概念：题库与版本（第二阶段）

`bank_questions` 集合中**一个文档 = 一个题目版本**：

- `root_id` 标识"题目家族"（同一道题的所有版本）
- `parent_id` 记录"这个版本从哪个版本改过来"（版本链 v1 → v2 → v3）
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
| 查看"这题被哪些问卷用了" | 按 `bank_ref.root_id` 反查问卷列表 |
| 查看"这题在所有问卷里的分布" | 按 `bank_ref.root_id` 聚合所有 `answers` |

前端入口：顶部导航「题库」→ 新建 / 共享 / 查看版本历史 / 查看使用情况 / 查看跨问卷统计；
问卷编辑器里的「📚 从题库选择」可直接把题库题加入当前问卷。

---

## 核心概念：条件跳转（next_rule）

每道题有一个 `next_rule` 字段，控制用户答完本题后下一题是什么：

| 模式 | 说明 |
|------|------|
| `mode: "default", fallback: "next"` | 默认下一题（顺序答题） |
| `mode: "default", fallback: "end"` | 结束问卷 |
| `mode: "by_option", fallback: "next", branches: [{when, goto}]` | 按选项跳转 |

### 数据结构示例

```json
{
  "mode": "by_option",
  "fallback": "next",
  "branches": [
    { "when": "选项A", "goto": 3 },
    { "when": "选项B", "goto": 5 }
  ]
}
```

### 使用说明

1. 在"添加题目"表单中，选择题型为**单选题**或**多选题**，填写选项
2. 将"答题后跳转"设为 **按选项跳转（单选）**
3. 下方出现每个选项的配置行，在数字框中填写该选项要跳转到的**题号**（题号从 1 开始）
4. 留空的选项默认走 `fallback`（下一题）

---

## 常见问题

### Q: 启动报错 `pymongo.errors.ServerSelectionTimeoutError`

MongoDB 未启动。请先启动 MongoDB：

```bash
brew services start mongodb-community   # macOS
# 或
mongod --dbpath /usr/local/var/mongodb
```

### Q: 启动报错 `ModuleNotFoundError: No module named 'app'`

在项目**根目录**执行 `uvicorn`：

```bash
cd survey_system
uvicorn app.main:app --reload
```

### Q: 问卷填写页面打不开 / Token 不生效

直接双击打开 `index.html` 时，URL 参数 `?token=xxx` 会被浏览器忽略。请使用方式二或方式三启动前端（通过 HTTP 服务器访问），参考上方「启动前端」章节。

### Q: 修改后端后没生效

确保后端用 `--reload` 参数启动：

```bash
uvicorn app.main:app --reload --port 8000
```

### Q: 想重置数据库

删除 MongoDB 中的 `survey_system` 数据库：

```js
// 在 mongo shell 中
use survey_system
db.dropDatabase()
```

---

## 环境变量（可选）

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SURVEY_MONGO_URI` | `mongodb://127.0.0.1:27017` | MongoDB 连接地址 |
| `SURVEY_MONGO_DB` | `survey_system` | 数据库名 |
| `SURVEY_BCRYPT_COST` | `12` | 密码哈希强度 |
| `SURVEY_TOKEN_LEN` | `7` | 问卷 Token 长度 |
| `SURVEY_MONGO_TIMEOUT_MS` | `5000` | MongoDB 超时（毫秒） |

---

## 交付物清单

按大作业要求（第一阶段 + 需求变更第二阶段），以下为需提交的完整文件清单：

### 代码

| 文件 / 目录 | 说明 |
|------------|------|
| `app/` | 后端全部代码（FastAPI 应用、路由、Repository、数据引擎、题库） |
| `frontend/` | 前端全部代码（HTML + CSS + JS，含题库模块） |
| `requirements.txt` | Python 依赖清单 |
| `tests/` | pytest 自动测试（9 个模块，136 条用例） |

### 文档

| 文件 | 说明 |
|------|------|
| `README.md` | 项目说明、启动方式、调试方法（本文档） |
| `docs/数据库设计.md` | MongoDB 集合设计、索引、关键查询示例（v2，含题库） |
| `docs/测试用例.md` | 第一阶段 17 条手工 + API 用例、第二阶段 27 条自动化用例 |
| `docs/项目完成报告.md` | 第一阶段完整项目报告（9 个章节） |
| `docs/项目完成报告（第二阶段）.md` | 第二阶段（题库 / 可复用题目）项目报告 |
| `docs/AI使用过程.md` | AI 协作日志，含 AI 做错 / 改对 / 设计的对账记录 |
