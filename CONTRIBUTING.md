# Contributing

VidSnap 的贡献指南维护在 [docs/contributing.md](docs/contributing.md)。

本地最短路径：

```bash
cp backend/.env.example backend/.env
cd backend && python -m pip install -r requirements.txt
cd ../frontend && npm ci
cd ..
./start_local.sh
```

提交前至少运行与改动相关的验证：

```bash
cd backend && pytest
cd frontend && npm run lint && npm run build
```

不要提交 `.env`、API Key、AccessKey、cookie、签名 URL、日志或大视频文件。
