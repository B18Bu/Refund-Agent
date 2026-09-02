

> **八维文化与产业研究院** | 2026年7月 | 北京八维信息集团
>

---

## 1 基本信息
| 项目 | 内容 |
| --- | --- |
| 工单对应的项目名称 | 多Agent 协同项目 |
| 工单编号 | 人工智能NLP-多Agent 协同-Agent 评测、成本优化与本地沙箱安全协作系统任务 |
| 工单类型 | AI 协作工单 |
| 创建时间 | 2026年7月19日 |
| 创建人 | 王洪荣 |


---

## 2 任务描述
### 一、任务描述
#### 1 项目背景
现有的"XXX"智能客服Agent（已经完成的Agent系统）在处理企业敏感的本地文件（如Word/Excel格式的用户报告、财务账单）时，存在严重的数据安全与系统被控风险。直接让LLM驱动的Agent在宿主机执行Python代码修改本地文件，容易受到Prompt注入攻击，导致系统越权、文件损毁或恶意代码执行。同时，旧系统System Prompt臃肿（Token消耗大）、多工具调用串行（Latency长）、且缺乏链路追踪与自动化评测基准。

本项目要求工单执行人从0到1构建**"Agent评测、成本优化与本地沙箱安全协作系统"**：

1. **<font style="background-color:#FBDE28;">本地安全沙箱与文件操作</font>****：** 集成腾讯云CubeSandbox安全沙箱技术与OfficeCLI命令行工具。构建一个端侧安全沙箱，使Agent只能在受限的沙箱容器内运行Python代码，自动读取Word/Excel文档，分析数据后使用Python将结果安全写回，避免污染宿主机系统。
2. **<font style="background-color:#FBDE28;">可观测性与评测</font>****：** 引入Langfuse/LangSmith链路追踪框架，对沙箱内的代码执行节点、LLM路由及工具调用进行全量Trace。构建10个典型业务场景的Golden Dataset，并基于LLM-as-a-judge架构进行自动化评测。
3. **<font style="background-color:#FBDE28;">优化治理</font>****：** 压缩System Prompt降低>=30% Token消耗，并将串行工具调用及沙箱任务重构为asyncio异步执行。

---

### 实施原则
+ **先护栏后开发：** 先建立AI协作规则（AGENTS.md）和验证闸门（Makefile/make check），再做设计和代码。
+ **文档先行：** 只分析业务目标、用户角色、核心流程、功能边界和待确认问题，不得编造不存在的业务背景，需求阶段严禁输出接口、数据库设计和代码。不确定的信息必须标记为"待确认"。
+ **单Loop聚焦：** 本工单仅设置1个完整Agentic Loop——"Agent提示词压缩与工具异步并行化优化"。其余可观测性集成、基础数据读取等作为基础任务。
+ **三方互评与裁决：** 需求分析阶段必须使用Gemini 3、Codex和工单执行人进行三方互评，并整理出"采纳/裁剪/延后/不采纳"表。
+ **代理式开发：** 编码阶段必须使用代理式AI工具（如Claude Code），由AI直接读取仓库、修改代码、运行Harness，严禁纯聊天式复制粘贴。

---

### 二、阶段开发任务
---

### <font style="background-color:#FBDE28;">任务一：需求分析、前后端架构设计与任务拆解（1.5人日）</font>
#### 1.1 三方对齐机制（Human + AI-A + AI-B）
在编写任何业务代码前，必须将原始需求发给逻辑分析型助手（如Gemini）与工程实现型助手（如Cursor/Claude Code/Codex）。有遇到需要决策的功能，由工单执行人做出明确决策并记录。

#### 1.2 三方主要职责分工
| **参与方** | **核心职责** | **关注焦点与架构设计沉淀** |
| --- | --- | --- |
| **人类 (学生/开发者)** | 1. 下达原始需求及已知限制；   2. 针对两个AI抛出的逻辑冲突、技术选型问题进行最终裁决；   3. 圈定 MVP 范围，砍掉过度设计。 | 业务合理性、开发工作量控制、系统最终交付质量。 |
| **AI-A (分析助手)   ****(例: Gemini)** | 1. **逆向转述需求并挖掘业务边界**（如 OCR 识别置信度过低、舆情风控接口超时该如何流转）；   2. 引导学生剖析异步队列与流量解耦（设计 FastAPI 接收请求后写入 Redis Streams，由后台 Worker 异步拉取执行的长周期推理模式）。 | 业务流闭环、异常场景防御、退赔安全策略、大模型调用流量解耦。 |
| **AI-B (编程助手)**   (例: Cursor) | 1. **评估技术栈可行性**（LangGraph、Redis Streams、FastAPI/Go 选型匹配度）；   2. 制定**物理规格草案**，剖析状态机无状态设计（挂起状态下利用 Redis Checkpointer 序列化上下文）与高并发防重（基于 Redis 分布式锁防重复审批）。 | 技术架构可行性、并发模型、状态序列化、接口规范与防重锁设计。 |


#### 1.3 实现步骤
**步骤1 - 启动逆向澄清：**

将需求发送给Gemini 3和Codex，要求只做需求理解，找出模糊点、冲突点，重点讨论：CubeSandbox的安全隔离边界与挂载目录权限、OfficeCLI的进程调用与输入净化、宿主机敏感数据外泄的漏沙检测、Telemetry SDK在沙箱环境内的通信与网络穿透限制。

> **启动Prompt模版：**
>
> 我现在有一个原始项目重构与新功能开发需求。  
请注意：本阶段只做需求分析，不写代码，不设计接口，不设计数据库。  
请你作为资深大模型工程专家、安全架构师和产品经理，帮我完成以下事情：
>
> 1. 用你自己的话转述这个需求，确认你理解的业务目标；
> 2. 分析目标用户、用户场景和核心业务流程（包含：Agent评测优化流、沙箱安全文件操作流）；
> 3. 拆出MVP必须功能、可选功能、暂不实现功能；
> 4. 针对以下技术与安全风险点进行深度剖析：
>     - **【评测与优化】：** 裁判模型Prompt的设计偏差风险、Telemetry对主业务时延的额外性能开销、串行工具调用改为异步并行时的异常捕获机制。
>     - **【沙箱安全】：** CubeSandbox与OfficeCLI交互时文件挂载的最小权限原则、如何防止沙箱内运行的Python代码越权访问宿主机、如何抵御Prompt注入导致的沙箱逃逸攻击，以及沙箱生命周期管理。
>     - **【链路追踪】：** 如何将沙箱内部Python脚本的执行日志与Trace ID隐式传播，并无阻塞地异步上报给外部的Langfuse/LangSmith监控端。
> 5. 找出可能超出1人1周范围的需求；
> 6. 给出需要我回答的问题清单。
>
> 原始需求如下：  
【重构并建设"Agent评测、成本优化与本地沙箱安全协作系统"。
>
> 1. 引入Langfuse链路追踪框架进行全量Trace，构建10个典型业务场景的Golden Dataset，编写基于LLM-as-a-judge架构的自动化评测脚本。
> 2. 对System Prompt进行压缩（Token消耗降低>= 30%），并将串行工具调用改为Python asyncio并行处理以降低P95时延。
> 3. 集成腾讯云CubeSandbox安全沙箱与OfficeCLI工具，让Agent能在隔离沙箱中安全运行Python代码，读取Word/Excel敏感文档，进行分析后再安全写回，拦截沙箱逃逸与非法命令注入。】
>

**步骤2 - AI交叉互评Prompt（发给对方AI）：**

> 下面是另一个AI对"Agent评测、优化与安全沙箱系统"同一需求的分析结果。请你只做需求评审，不写代码，不做接口和数据库设计。  
请输出：
>
> 1. 这份需求分析遗漏了什么？
> 2. 哪些需求边界不清？
> 3. 哪些功能可能过度设计？
> 4. 哪些内容不适合1人1周内完成？
> 5. 哪些问题必须由工单执行人确认？
> 6. 你建议保留、删除、延后的内容。	
>

 						

<font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">[</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">此处粘贴另一个 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">AI </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">的输出内容</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">] </font>



**步骤3 - 输出需求文档：** 整理最终《需求分析文档》和《WBS任务拆解表》。

---

### <font style="background-color:#FBDE28;">任务二：基于AI编程工具的代码生成、功能实现与测试（3.0人日）</font>
				

功能描述 在正式编码前，建立 AI 开发护栏，并使用 Superpowers 的 brainstorming -> writing-plans 流程确定设计规格并输出可执行计划。 实现步骤:

#### 2.1 开发准备：建立AI开发护栏
本环节只建立护栏，不做具体功能开发。

+ 创建**AGENTS.md**，明确项目目标、AI行为规则（如：异步并行调用必须使用`asyncio.gather(..., return_exceptions=True)`等防崩溃规则）及禁止修改范围。
+ 创建**Makefile**，提供统一的验证闸门`make check`（包含格式检查和单元测试）。

#### 2.2 设计规格：用Superpowers生成可执行计划
+ 启动Agent，调用Superpowers逐段展示设计，每一段等待人工确认。
+ 必须确定的内容：10个核心测试用例的输入输出边界、LLM-as-a-judge的三维打分准则、超时与局部熔断策略、Trace上报失败的本地缓存降级方案。
+ 确认无误后，将设计写入`docs/design.md`。
+ 生成实现计划：调用Superpowers生成docs/implementation-plan.md，明确修改文件、测试命令和人工确认点。

```json
brainstorming启动示例：

请使用Superpowers brainstorming skill，为本项目生成可开发的设计规格。
请先读取项目需求文档（docs/requirements.md）、AGENTS.md、现有代码和测试。
基础功能只做必要设计。本次需要详细设计和执行完整Agentic Loop的模块是"Agent提示词压缩、工具异步并行化，以及本地安全沙箱文件操作集成"。
请按brainstorming流程逐步进行：
1. 每次只问一个设计问题（包含：评测三维指标计算、Prompt语法树压缩方案、asyncio.gather异常隔离、CubeSandbox挂载卷与OfficeCLI进程净化、沙箱内Trace ID的隐式传递）；
2. 存在多种方案时，先说明利弊和推荐方案；
3. 按段落分步展示"数据模型、状态机、评测判定算法、沙箱生命周期与安全机制、接口与异常处理、测试用例"设计，每段等待我回复确认；
4. 未经我批准设计前，不要写代码。
最终将已批准设计写入docs/design.md。

```

#### 2.3 Agentic Loop开发
基于已批准的`docs/design.md`，由实现Agent A与评审Agent B配合完成。以自动化闭环(Agentic Loop)的形式完成“提示词压缩与工具异步并行化”的开发、测试、Review 和人工验收。

**进入Loop的前提条件：**

+ `docs/design.md`和`docs/implementation-plan.md`已经人工批准
+ 前置功能（如Langfuse基础SDK集成、Golden Dataset加载）已可运行
+ 开始Loop前运行`make check`并通过

**Loop执行规则：**

**实现Agent A（Claude Code主会话）： 	**编写测试用例，实现 Prompt 剪裁剪治，重构为 asyncio 并行 Tool Calls，运行 Harness 验证。

<font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">请作为</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">“实现 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">Agent </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">A”</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">，严格根据已批准的 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">docs/design.md 和 docs/implementation-plan.md 执行开发任务。  
</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">本次唯一需要执行完整 Agentic </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">Loop 的是“Agent </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">提示词压缩与工具异步并 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">行化”以及“本地安全沙箱文件读写”模块。</font>

****

1. 不要擅自修改鉴权、权限、数据库迁移和环境变量；
2. 修改代码前，先说明影响范围、预计修改文件和风险点；
3. **【安全规范】：** 沙箱内文件读写严禁使用shell=True调用外部命令；所有Word/Excel操作代码必须封装在沙箱隔离环境内；沙箱实例必须使用try...finally确保在执行结束后被销毁；
4. **【性能与并发】：** 异步并行调用必须使用`asyncio.gather(..., return_exceptions=True)`避免整链崩溃；确保Telemetry SDK上报Trace时不阻塞FastAPI主事件循环；
5. 每次修改后运行`make check`；
6. 验证通过后，输出代码变更diff和测试日志，等待评审Agent B审查。

 						

<font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">现在，</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">请开始执行计划中的第一步</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">:为 10 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">个黄金用例编写自动化评测基准测试</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">， </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">并集成 Langfuse </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">SDK </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">记录初始 Trace 数据。 </font>



**评审Agent B（基于.claude/agents/ticket-reviewer.md的Subagent）： **仅读取代码 diff、测试日志与落盘文件，对代码一致 性、并发安全进行严格评审。输出 P0/P1/P2 级别的审查报告，禁止直接修改代码。		

<font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">你是工单状态流转与沙箱安全协作 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">Loop </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">的评审 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">Agent B。  
</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">请读取 AGENTS.md</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">、</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">docs/design.md</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">、 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">docs/implementation-plan.md</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">、git status --short、git diff HEAD </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">以及测试运行日志。 </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">请对本次代码变更进行安全、一致性与性能审查，禁止修改任何代码。</font>

** 	 **

按P0 <font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">(阻断合并的安全与核心功能缺陷) </font>/P1(<font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">违反设计规格或缺少测</font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">试</font>)/P2<font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">(优化建议)</font>级别输出评审报告，重点审查：

1. **【沙箱安全】：** 代码中是否存在命令注入漏洞？OfficeCLI输入是否净化？<font style="color:rgb(22.000000%, 22.700000%, 25.900000%);">Agent </font><font style="color:rgb(22.000000%, 22.700000%, 25.900000%);background-color:rgb(96.500000%, 97.300000%, 98.000000%);">在沙箱内执行 Python时是否能越权读写宿主机 目录?</font>
2. **【沙箱生命周期】：**   在读取 Excel/Word 发生异常(如文件损坏、超时) 时，沙箱是否能在 finally 块中被 100% 销毁?是否存在孤儿容器风险?
3. **【并发与异步】：** Python asyncio 并行调用中，是否正确使用了 return_exceptions=True?单个工具报错是否会引起整链崩溃?
4. **【Telemetry性能】：** Langfuse Telemetry 发送 Trace 时是否 引入了同步阻塞，导致主 API 响应时延翻倍?沙箱内的 Trace 上报是否能 正常穿透并关联到宿主机 Trace 树?
5. **【指标对齐】：** 优化后的System Prompt Token是否降低了30%以上？LLM-as-a-judge得分是否未下降？

  请在最终回复中输出完整评审报告。不接受调用方对实现的任何口头解释， 只根据真实代码、diff 和日志说话。

			

**人工干预**:只在 Agent A 陷入死循环或无法通过 Harness 时介入。 

---

### <font style="background-color:#FBDE28;">任务三：打包上线与压力测试（2.5人日）</font>
  在 AI 运维助手的协同下，将系统容器化部署至服务器并执行高并发压力测试。

#### 3.1 一键容器化
+ 使用 Docker Compose 部署服务并使用 Locust 进 行高并发压力测试，验证系统的高可用性与自愈能力。
+ 配置容器自启动。手动执行`docker kill`强杀Web容器，验证服务在5秒内自动拉起恢复，且Trace上报通道自动重连。



#### 3.2 高可用容灾验证: 
 编写 docker-compose.yml，启动 Web 后端、Redis、 服务。  

 配置容器自启动。手动执行 docker kill 强杀 Web 容器，验证服务是否在 5 秒内自动拉起恢复，且 Trace 上报通道自动重连。。

#### 3.3 压力测试自证
编写Locust脚本，模拟调度员批量查询运单、并发提交改派的高并发场景。

| 等级 | QPS | P95延迟 | 错误率 |
| --- | --- | --- | --- |
| 合格 | >= 200 | < 300ms | < 0.1% |
| 良好 | >= 500 | < 300ms | < 0.1% |
| 优秀 | >= 1000 | < 300ms | < 0.1% |


---

### <font style="background-color:#FBDE28;">任务四：项目总结与AI代码审查报告（1人日）</font>
完成代码开发后，启动审查 Agent，输出 docs/ai-review.md。审查必 须覆盖:

#### 4.1 AI代码审查报告
审查必须覆盖：

+ Telemetry SDK异步上报是否阻塞了API响应主线程。
+ asyncio.gather是否未配置return_exceptions=True导致单个工具报错使整个Agent链路崩溃。

#### 4.2 项目总结与AI编程复盘
工单执行人手动编写`docs/project-retrospective.md`，梳理从"三方会谈"到"Agentic Loop"的AI协同开发心得。防范“氛围编 程(Vibe Coding)”带来的不可控隐患。

#### 4.3 沉淀面试QA库
提炼3个与本项目紧密相关的核心面试题，并给出标准解答。

---

## 工时预估
**7 人日**

---

## 产出物
| 类别 | 交付成果物 |
| --- | --- |
| 需求文档 | 《需求分析与WBS拆解文档》、《三方需求互评与对齐记录》 |
| 项目源码 | agent-eval-project/ 全栈源码（含沙箱驱动与安全策略） |
| 设计文档 | docs/design.md、docs/implementation-plan.md |
| AI护栏 | AGENTS.md（含沙箱安全协作规则）、Makefile |
| 测试 | 10个Golden Dataset、单元测试、Locust压测脚本 |
| 部署 | docker-compose.yml |
| 报告 | ai-review.md、deploy-report.md、project-retrospective.md |
| 面试QA | 沉淀的面试QA库与优秀Prompt模板 |


---

## 验收标准
+ **沙箱安全与文件写回红线：** 所有Word/Excel文件的读取、解析、修改与写回必须100%在CubeSandbox沙箱容器中进行。宿主机除了映射的data目录外，任何系统路径不得被Agent越权写或执行。成功抵御至少2类Prompt注入导致的逃逸测试。
+ **成本优化红线：** System Prompt压缩后Token消耗减少>=30%。
+ **性能提升红线：** 重构并行化后，Agent整体流程（不含大模型本身推理及沙箱硬启动时间）平均响应时延降低>=40%。
+ **高可用红线：** 在高并发压测下，服务不可崩溃，沙箱实例在任务结束后100%自动回收；强杀Web服务后5秒内自愈。

---

## 备注
---



