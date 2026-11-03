// 机读对拍测试(taskEvents.test.ts 读 backend/ipdb/_tasks.py 抽 _OPS_LOG_KEEP)
// 需要 node:fs/node:path/node:url;tsconfig.app.json 的 types 闭集只有
// vite/client + @testing-library/jest-dom,不含 node(tsconfig.node.json 有,
// 但只覆盖 vite.config.ts),文件级 /// <reference types="node" /> 在该配置下
// 解不开 node: 前缀模块名(TS2591)。票 #292 边界 = 只动 frontend/src/tasks/**,
// 故本文件以最小 ambient 声明钉住测试用到的 4 个签名(vitest 运行时走真
// Node 内建,不受影响)。
// 移除条件:tsconfig.app.json 的 types 数组收录 "node" 时,本文件应删。
declare module "node:fs" {
  export function readFileSync(path: string, encoding: string): string;
}
declare module "node:path" {
  export function dirname(p: string): string;
  export function join(...parts: string[]): string;
}
declare module "node:url" {
  export function fileURLToPath(url: string): string;
}
