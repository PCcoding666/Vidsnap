# VidSnap Frontend

VidSnap 前端是 Vite + React + TypeScript + Tailwind CSS + shadcn/ui。根目录 [README.md](../README.md) 是项目主入口；本文只记录前端开发要点。

## 本地开发

```bash
npm ci
npm run dev -- --port 8081 --host 0.0.0.0
```

默认访问：

```text
http://localhost:8081
```

完整本地环境建议从仓库根目录启动：

```bash
../start_local.sh
```

或在根目录运行：

```bash
./start_local.sh
```

## 常用命令

```bash
npm run dev
npm run lint
npm run build
npm run preview
```

## 目录结构

```text
src/
├── components/        # shared and feature UI
├── components/ui/     # shadcn/ui primitives
├── config/            # frontend config helpers
├── contexts/          # React context
├── i18n/              # translations
├── integrations/      # legacy Supabase client/types
├── pages/             # route screens
└── services/          # API client and API types
```

## API 配置

开发环境中 `src/services/api.ts` 使用 `/api/v1` 作为 base URL，依赖 Vite 代理或同源代理转发到 FastAPI。生产构建使用：

```bash
VITE_API_BASE_URL=https://vidsnap.example.com/api/v1
```

更多配置见 [docs/configuration.md](../docs/configuration.md)。

## 开发规则

- 新页面放在 `src/pages/`。
- 可复用业务组件放在 `src/components/`。
- shadcn/ui primitive 放在 `src/components/ui/`。
- API 类型和请求方法优先维护在 `src/services/api.ts`。
- 可见 UI 改动提交前运行 `npm run lint` 和 `npm run build`。
