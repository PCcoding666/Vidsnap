// VidSnap demo 采集:真实浏览器走完整链路(上传→运行→trace→产物),按阶段截图
import { chromium } from 'playwright';

const OUT = process.env.OUT_DIR || '.';
const VIDEO = process.env.DEMO_VIDEO;
const BASE = 'http://localhost:8081';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 });

console.log('1. 打开工作台…');
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/01-workspace-idle.png` });

console.log('2. 上传 demo 视频…');
await page.setInputFiles('input[type=file]', VIDEO);
await page.waitForTimeout(600);

console.log('3. 点击运行工具链…');
await page.click('button:has-text("运行工具链")');

// 等 trace 进入执行状态,截"执行中"镜头(约转录阶段)
console.log('4. 等待执行中状态…');
await page.waitForSelector('text=执行中', { timeout: 20000 });
await page.waitForTimeout(12000); // 让 trace 点亮几步(ingest/转录进行中)
await page.screenshot({ path: `${OUT}/02-trace-running.png` });
console.log('   已截执行中镜头');

// 等运行结束(按钮文案恢复),上限 6 分钟
console.log('5. 等待完成…');
await page.waitForSelector('button:has-text("运行工具链")', { timeout: 360000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/03-trace-succeeded.png` });
await page.screenshot({ path: `${OUT}/04-full-page.png`, fullPage: true });
console.log('   已截完成镜头');

// 页面上是否有报错提示?
const err = await page.locator('text=⚠').count();
console.log(err > 0 ? 'WARN: 页面出现错误标记,检查 03 截图' : 'OK: 无错误标记');

await browser.close();
console.log('DONE');
