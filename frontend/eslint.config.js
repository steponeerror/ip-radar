import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'
import requireMockReset from './eslint.rules/require-mock-reset.mjs'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    // #304-⑦:vi.mock 而无显式复位(mockReset/resetAllMocks 族)会跨用例泄漏 mock 状态。
    // clear 族(只清调用史不剥实现)不算复位;豁免区在下一块,只进不出。
    files: ['src/**/*.test.{ts,tsx}'],
    plugins: { ipradar: { rules: { 'require-mock-reset': requireMockReset } } },
    rules: { 'ipradar/require-mock-reset': 'error' },
  },
  {
    // #304-⑦ 豁免区(只进不出,新文件不得入内):共同理由 = vi.mock 工厂内联了
    // mockResolvedValue 默认值,resetAllMocks 会把默认值一并剥掉,后续用例拿到
    // undefined;按本票「不改测试行为,只加防线」的边界,存量豁免、待夹具重构时再摘:
    // - DbStatusBar.test.tsx:工厂默认值 + 用例内 Once(均在本用例消费),无持久泄漏
    // - DbStatusBar.demo.test.tsx:纯静态工厂默认值,用例零实现覆盖,无跨用例写面
    // - App.test.tsx:静态工厂默认值(getDbStatus/getVersion),用例零实现覆盖
    // - SourcesPage.test.tsx:工厂默认值 + 26 处 Once(均本用例消费);beforeEach 只清 localStorage
    // - OpsPage.test.tsx:工厂默认值面广(9 枚)+ beforeEach 只补播 2 枚,换 reset 需全量重排夹具
    files: [
      'src/components/__tests__/DbStatusBar.test.tsx',
      'src/components/__tests__/DbStatusBar.demo.test.tsx',
      'src/__tests__/App.test.tsx',
      'src/pages/__tests__/SourcesPage.test.tsx',
      'src/pages/__tests__/OpsPage.test.tsx',
    ],
    rules: { 'ipradar/require-mock-reset': 'off' },
  },
])
