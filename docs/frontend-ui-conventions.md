# 前端 UI 规范(硬性)

给 agent 的前端 UI 硬规则。违反会直接造成可见的体验问题,必须遵守。

## 图标按钮必须是正方形

只放一个图标的按钮(垃圾桶、加号、播放等)**必须正方形**,不能做成"高度偏高的长方形"。

写法上同时满足以下几条,任何一条漏掉都可能被别处的 `min-height` 撑高:

```css
.icon-btn {
  box-sizing: border-box;   /* 边框不额外撑高 */
  width: 30px; height: 30px;
  min-width: 30px; min-height: 30px;  /* 锁死,别让全局 min-height 赢 */
  aspect-ratio: 1 / 1;       /* 兜底,任何情况下都保持方形 */
  padding: 0; line-height: 0;
  display: inline-flex; align-items: center; justify-content: center; /* 图标居中 */
}
```

要点:
- **width == height == min-width == min-height**。本仓库有大量 `min-height: 34px !important` 的按钮基类,只写 `height` 会被它们撑成长方形。
- 无边框默认、`:hover` 才出轮廓的图标按钮:`border: 1px solid transparent`,hover 时给 `border-color`,不要用 `outline`(会偏移)。
- 图标用 `flex` 居中,不要靠 padding 凑。
- 复用已有图标(lucide 风格的 path),不要自造 UI;参考 `web/static/spelling-drill.js` 的 `.nr-card-tool`。
