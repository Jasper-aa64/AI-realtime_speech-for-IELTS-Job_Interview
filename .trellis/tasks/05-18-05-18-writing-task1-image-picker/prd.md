# Writing Task 1 图表题选题窗口与配图

## 背景

当前写作页 Task 1 只有下拉框选题，题目没有对应图表。Academic Task 1 本质上必须看图表/地图/流程图作答；只显示文字会让练习失真。

## 目标

- 每个 Task 1 Academic 题目支持 `image_url`。
- 本地 seed 题库同步时把 `image_url` 写入 Django `WritingPrompt`。
- 写作页不再主要依赖下拉框，改为可浏览的选题窗口。
- Task 1 选题窗口里展示图表缩略图，选中后主面板展示对应大图。
- 静态图片由 Django 服务从 `web/static/assets/...` 提供。
- 不能直接搬运未授权的剑雅原题/原图；保留数据结构，支持导入授权材料。

## 非目标

- 不抓取或内置 Cambridge IELTS 版权原题/原图。
- 不重构整套写作评分流程。
