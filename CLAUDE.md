# 仓库指南

## 项目结构与模块组织

本仓库是一个 AI 角色流水线原型，包含 Vue 前端和 FastAPI 后端。

- `front/`：Vue 3 + Vite 单页应用。源码在 `front/src/`，其中 `App.vue` 是主界面，`api.js` 负责后端请求，`styles.css` 放全局样式。
- `backend/`：FastAPI 服务。应用代码位于 `backend/app/`。
- `backend/app/api/routes/`：资源、角色、视频、动作捕捉、表情捕捉等 HTTP 路由模块。
- `backend/app/models/`：Pydantic 请求与响应模型。
- `backend/app/providers/`：外部模型服务适配器和 mock provider。
- `backend/app/services/`：本地存储、资源管理、任务管理服务。
- `backend/data/`：运行时生成的本地任务、资源和日志。将其视为本地状态，不作为源码提交。
- 根目录 `*.md`：产品说明、架构说明和项目文档。

# 全局回复设定
1.用中文进行回复，注释和log 也都使用中文，但函数名和变量名等实际代码不要用中文
2.代码注释要完整清晰，主要的代码逻辑都需要注释

# 工程开发原则
## 简单性原则 (Simplicity First)
**核心：** 遵循“少即是多”哲学。绝不进行不必要的抽象，绝不引入非必需的依赖。
- **反过度工程:** 简单的函数和数据结构优于复杂的接口和继承体系。
## 明确性原则 (Clarity and Explicitness)
**核心：** 代码的首要目的是让人类易于理解。

# 开发和测试环境
后端是python3.13,使用 conda activate 313环境