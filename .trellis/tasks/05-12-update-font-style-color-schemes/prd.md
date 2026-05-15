# PRD: Update Font Style Color Schemes

## Objective
Update the color schemes for "Default" and "Popular/Creative" font styles to match modern AI assistant UIs.

## Requirements

### Default Style (参考 ChatGPT UI)
- **Sidebar**: Deep dark gray (#171717 / #202123)
- **Main content**: White/light gray background
- **Accent**: Teal/Green (#10a37f) - ChatGPT's signature accent
- **Text**: High contrast dark text on light backgrounds
- **Overall feel**: Clean, professional, dark sidebar with bright content area

### Popular/Creative Style (参考 Gemini UI)
- **Sidebar**: Light with subtle blue tint
- **Main content**: Light background with gradient accents
- **Accent**: Blue-purple gradient (#4285f4 → #9b72cb → #d946ef)
- **Vibrant, playful colors**
- **Gradient buttons and highlights**
- **Overall feel**: More colorful, energetic, modern tech aesthetic

## Files to Modify
- `web/static/styles.css` - Update CSS custom properties for each font style

## Scope
- Only color scheme changes via CSS custom properties
- No structural changes to the layout
- Keep Academic style as-is (already matches Claude style)
