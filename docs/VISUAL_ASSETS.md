# 视觉素材与提示词

使用内置 image_gen（未使用 CLI／API 回退）生成，最终素材已复制进项目：

- `web/images/food-atlas.png`：16 宫格菜品示意图，由 CSS 方形裁切定位到各菜，不改变原始图片。
- `web/images/dinner-hero.png`：首页横幅食物特写。

这些是 AI 生成的写实食物示意图，并非用户真实做菜照片。界面已标注；热量来自菜谱食材与份量，不从图片推测。自建菜谱如果没有对应素材，显示明确的缺图占位，避免套用不相干的照片。

## 视觉方向

米白近白背景 `#FAF8F5`，酱油褐文字 `#32231D`，辣椒红动作 `#E94B2C`，姜黄色辅助 `#FFB851`。采用系统中文无衬线重字标题；横向导航与大幅菜品特写，突出食物质感，把助手、天气和摄入信息放到安静的辅助区域。手机端保留图片和完整功能，导航可横向滚动。

## food-atlas 最终提示词

```text
Use case: photorealistic-natural. Asset type: a single high-resolution food photography atlas for a Chinese home cooking app, NOT a UI mockup. Create ONE perfectly aligned 4-by-4 contact sheet containing 16 equal square photographs, no gutters, no borders, no lettering, no numbers, no watermarks. Each photograph should have its entire main plate centered with tight delicious editorial food photography, three-quarter or top-down framing, richly textured real food, appetizing glossy sauces, natural window light, subtle steam where appropriate, varied ceramics and wooden tabletop tones. Exactly follow this row-major dish list, each panel is its own separate photo: row 1: (1) tomato and silken tofu soup with bright tomato chunks, (2) steamed chicken pieces with shiitake mushrooms, (3) broccoli with pink shrimp stir fry, (4) Chinese yam egg-drop soup with small carrot cubes and greens. Row 2: (5) chicken cubes with red yellow green bell peppers, (6) creamy golden pumpkin millet porridge, (7) refreshing smashed cucumber and black wood-ear mushroom salad, (8) rich braised beef and white radish stew. Row 3: (9) spinach and egg noodle soup, (10) whole steamed sea bass with ginger and scallions, (11) celery stir-fried with sliced firm smoked tofu, (12) sweetcorn carrot pork rib soup. Row 4: (13) juicy tomato and scrambled eggs stir fry, (14) golden pan fried tofu squares with scallions and soy glaze, (15) crisp lotus-root snow pea carrot wood-ear vegetable stir fry, (16) sweet potato oatmeal bowl with milk. Make every dish visibly distinct and unmistakably recognizable. The color and texture should make the viewer hungry, restaurant-quality photography of attainable Chinese home food. Keep all 16 equal cell boundaries exactly at quarters of the image. Aim for a 2048 by 2048 square image.
```

## dinner-hero 最终提示词

```text
Use case: photorealistic-natural. Asset type: landscape hero food photograph for a Chinese home recipe app. A spectacular yet attainable Chinese home dinner on a rich dark brown wooden table: in the foreground right, a shallow rustic white ceramic plate piled with glossy golden chicken cubes, red and yellow peppers, green scallions, a few tiny steam wisps, sharply rendered succulent texture; at the back a small bowl of steamed rice and a faint blurred tomato egg stir fry bowl. Tight intimate restaurant editorial photography, raking natural side light, warm saturated but believable colors, shallow depth of field, no people. Composition: landscape 3:2 image, main enticing food occupies right two thirds, left third stays dark softly textured wooden tabletop with gentle depth, designed for white headline overlay added later in code. Absolutely no text, no logos, no borders, no collage. Real photography aesthetic, not illustration or 3D render.
```
