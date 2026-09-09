# 「确认路径」Logo 资产实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 交付可直接引用的「确认路径」SVG 标识及其使用规范，不改动当前前端页面。

**架构：** 将四个无脚本、无外部依赖的 SVG 文件统一存放在 `frontend/src/assets/brand/`。SVG 共享 `0 0 90 90` 坐标系，并以不同的颜色方案支持浅色、深色和单色媒介；规范文件定义最小尺寸、留白和禁用方式。

**技术栈：** SVG 1.1、Markdown、PowerShell XML 解析。

---

## 文件结构

- 创建：`frontend/src/assets/brand/brand-mark.svg`：默认彩色图标。
- 创建：`frontend/src/assets/brand/brand-mark-reverse.svg`：深色页面使用的反白图标。
- 创建：`frontend/src/assets/brand/brand-mark-monochrome.svg`：打印和单色媒介的图标。
- 创建：`frontend/src/assets/brand/brand-logo-horizontal.svg`：包含图标与中英字标的宽屏锁定版本。
- 创建：`frontend/src/assets/brand/brand-guidelines.md`：颜色、尺寸、留白与禁用规范。

### 任务 1：建立可验证的彩色图标资产

**文件：**
- 创建：`frontend/src/assets/brand/brand-mark.svg`

- [ ] **步骤 1：编写失败的结构测试**

运行以下 PowerShell 断言，文件尚未存在时应失败：

```powershell
[xml](Get-Content -Raw 'frontend/src/assets/brand/brand-mark.svg')
```

- [ ] **步骤 2：确认失败原因**

运行：`[xml](Get-Content -Raw 'frontend/src/assets/brand/brand-mark.svg')`

预期：PowerShell 报告找不到该路径。

- [ ] **步骤 3：创建最小 SVG 实现**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 90 90" role="img" aria-label="品牌优选确认路径标识">
  <rect x="4" y="4" width="82" height="82" rx="20" fill="#287eb7"/>
  <path d="M21 47h17l9-17 17 28H47l-9 12-17-23z" fill="#fff"/>
  <circle cx="65" cy="29" r="11" fill="#f1ae42"/>
  <path d="m60 29 3 3 6-7" fill="none" stroke="#fff" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

- [ ] **步骤 4：运行结构验证**

运行：`[xml](Get-Content -Raw 'frontend/src/assets/brand/brand-mark.svg'); 'PASS'`

预期：输出 `PASS`。

### 任务 2：建立媒介颜色变体

**文件：**
- 创建：`frontend/src/assets/brand/brand-mark-reverse.svg`
- 创建：`frontend/src/assets/brand/brand-mark-monochrome.svg`

- [ ] **步骤 1：编写失败的存在性测试**

```powershell
Test-Path 'frontend/src/assets/brand/brand-mark-reverse.svg'
Test-Path 'frontend/src/assets/brand/brand-mark-monochrome.svg'
```

- [ ] **步骤 2：确认失败原因**

运行上述命令。

预期：两行均输出 `False`。

- [ ] **步骤 3：创建反白和单色 SVG**

两个文件保留任务 1 的相同图形路径和坐标系；反白版使用 `#5fc7ed` 底色及 `#173d61` 路径，单色版全部使用 `#173d61` 填充与描边。

- [ ] **步骤 4：运行 XML 与颜色验证**

运行：`Get-ChildItem 'frontend/src/assets/brand/brand-mark-*.svg' | ForEach-Object { [xml](Get-Content -Raw $_); $_.Name }`

预期：输出两个文件名且无 XML 解析错误。

### 任务 3：建立横向字标和使用规范

**文件：**
- 创建：`frontend/src/assets/brand/brand-logo-horizontal.svg`
- 创建：`frontend/src/assets/brand/brand-guidelines.md`

- [ ] **步骤 1：编写失败的内容检查**

```powershell
Test-Path 'frontend/src/assets/brand/brand-logo-horizontal.svg'
Test-Path 'frontend/src/assets/brand/brand-guidelines.md'
```

- [ ] **步骤 2：确认失败原因**

运行上述命令。

预期：两行均输出 `False`。

- [ ] **步骤 3：创建横向字标和规范**

横向 SVG 使用宽高比约 `330:90`，引用图标的同一图形结构，并通过 `<text>` 提供 `品牌优选` 和 `CONFIDENT SERVICE`。规范必须列出：24 px 图标下限、32 px 横向字标下限、20% 留白、浅色/深色/单色选择规则，以及禁止改色、变形、阴影、渐变和拆分字标。

- [ ] **步骤 4：运行内容与安全检查**

运行：`rg -n "(http:|https:|<script|base64|TODO|C:\\|D:\\)" frontend/src/assets/brand`

预期：无输出且进程退出码为 1；表示文件未包含外部资源、脚本、位图数据、占位内容或本机路径。

### 任务 4：完成静态资产回归验证

**文件：**
- 验证：`frontend/src/assets/brand/*.svg`
- 验证：`frontend/src/assets/brand/brand-guidelines.md`

- [ ] **步骤 1：验证 SVG 坐标系与最小可读性约束**

运行：`rg -n 'viewBox="0 0 90 90"|aria-label="品牌优选确认路径标识"' frontend/src/assets/brand/*.svg`

预期：四个 SVG 都匹配 90 单位坐标系与中文无障碍标签。

- [ ] **步骤 2：运行前端生产构建**

运行：`npm --prefix frontend run build`

预期：命令退出码为 0；允许既有 bundle 大小提示，不能有构建失败。

- [ ] **步骤 3：检查变更范围**

运行：`git diff --check; git status --short`

预期：没有空白错误；本次新增内容仅位于 `frontend/src/assets/brand/` 与该计划文档，工作区原有改动保持原样。

- [ ] **步骤 4：提交本次资产**

```powershell
git add frontend/src/assets/brand docs/superpowers/plans/2026-09-09-confirmation-path-logo-assets.md
git commit -m "feat: 添加确认路径品牌标识"
```

预期：提交只包含上述 Logo 资产、规范和计划，不包含工作区已有改动。

## 自检结果

- 规格覆盖：任务 1-3 覆盖四个 SVG、规范和所有使用规则；任务 4 覆盖可解析性、安全性、构建与范围验证。
- 占位符：计划没有待定事项或泛化测试描述。
- 一致性：所有图标均使用 90 单位坐标系；所有文件集中于同一资产目录；页面接入不在本计划范围内。
