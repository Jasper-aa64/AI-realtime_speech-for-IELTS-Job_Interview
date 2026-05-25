# Global UI/UX Review 记录（2026-05-25）

## 1. 已直接修改的内容和原因

- 写作报告卡片标题：补齐 compact report payload 的 `prompt`，并让前端在无 source 的旧记录中使用 `Task 2 • 观点类` / `Task 1 Academic • 表格` 这类结构化 fallback，避免显示裸主题名如 `Technology And Learning`。
- 写作报告 rail：标题改为 `Writing Reports`，副文案改为更明确的“横向滑动查看历史”，并把上一条/下一条从字符箭头换成固定尺寸的 SVG 图标按钮。
- 口语/写作报告 rail：统一上一条/下一条按钮的 SVG 尺寸、hover、focus 和阴影，减少文本箭头在不同字体下的跳动。
- 全局 CSS tokens：新增 radius、border、shadow、motion tokens，并把 panel、rail、icon button、prompt choice、writing cards、corpus cards 等高频界面元素逐步接入。
- Motion：保留 150-300ms 范围内的 hover/active/focus 动效，并补强 `prefers-reduced-motion`，让动画和过渡在用户减少动态效果时基本停用。
- 写作报告空列表：从直接文本改为复用 `history-empty-state`，让空态在 rail 里尺寸稳定。

## 2. 使用的 UI 原则/tokens

- `--radius-md` / `--radius-lg` / `--radius-xl` / `--radius-pill`：普通按钮和卡片保持 8-12px，pill 仅用于标签、圆形按钮和分段控件。
- `--border-soft` / `--border-strong`：列表、rail、卡片先用浅边界，active/focus 再强化。
- `--shadow-xs` / `--shadow-sm` / `--shadow-md`：默认少阴影，hover 和 active 才增加层级。
- `--motion-fast` / `--motion-base`：交互反馈控制在 160ms / 220ms，避免页面显得跳。
- 工作型 IELTS 应用原则：优先信息密度、可扫描性、稳定尺寸和清楚的操作状态，不做营销 hero、不加装饰 blob/orb、不引入新框架。

## 3. 刻意没有改的内容

- 没有重做整体视觉主题、导航结构或首页，因为当前任务是全局 review 后的 confident improvements，不是完整 redesign。
- 没有把所有历史 CSS 一次性 token 化；当前文件已有大量既有样式，过大替换容易引入布局回归。
- 没有改写 P1/P2/P3 的练习流程和计时逻辑，只处理视觉一致性和报告标题/rail 可读性。
- 没有新增前端框架或 icon 依赖；继续使用当前 plain HTML/CSS/JS 结构。
- 没有修改数据库字段或迁移；写作报告标题所需信息通过现有 payload 字段解决。

## 4. 拿不准、留给用户明早 review 的问题

- 写作报告 rail 的英文标题 `Writing Reports` 是否要改成中文 `写作报告`，以便和详情页更统一。
- 历史报告 rail 的普通 speaking attempts 是否也要把 `Reports / 横向滑动` 改成更中文、更具体的文案。
- 当前 app 有 `Default / Academic / Popular` 三套字体主题；是否保留 Popular 模式里较强的多彩按钮视觉，还是进一步收敛成更工作型的风格。
- 写作报告卡片是否需要显示更短标题，例如移动端将 `剑雅20-1 • Clean Water • 观点类` 缩成 `剑雅20-1 • Clean Water`。
- 是否继续第二轮清理旧 CSS 中重复/注释掉的 history 样式块，降低后续维护成本。

## 5. 手动 QA checklist

- 打开 Writing Reports，确认 Cambridge Task 2 卡片显示类似 `剑雅20-1 • Clean Water • 观点类`。
- 打开 Writing Reports，确认 Cambridge Task 1 卡片显示类似 `剑雅20-1 • 表格`。
- 找一条无 source 的旧 Task 2 写作记录，确认卡片/详情标题显示类似 `Task 2 • 观点类`，不显示裸 `Technology And Learning`。
- 找一条无 source 的旧 Task 1 Academic 写作记录，确认标题显示类似 `Task 1 Academic • 表格`。
- 横向滚动 speaking history rail 和 writing report rail，确认左右按钮尺寸稳定、hover/focus 可见、disabled 状态清楚。
- 在 P1/P2/P3 练习页检查返回按钮、录音按钮、黄色素材提示按钮没有遮挡或跳动。
- 在 P2 corpus 和 takeaway 页面检查列表 hover、删除按钮、弹窗关闭按钮仍然可用。
- 在 Writing 选题弹窗检查 Task 1 图片卡、Task 2 文本卡、category/source filter 没有文字溢出。
- 在移动宽度（约 375px 和 640px）检查写作 topbar、报告 rail、prompt picker、详情卡片没有重叠。
- 开启系统 reduced motion 后检查页面仍可操作，动画/过渡明显减少。
