# Output format

The rendered response fragment begins directly with the first quotation or unlinked historical note. Do not repeat the current Apple Note text. Do not add headings such as “与你这句话有关” or “Reading Mirror 回答”. The guarded Apple Notes writer, not the renderer or model, adds a separate local `YYYY年MM月DD号` line before the generated fragment.

## Citation block invariant

Treat every verified book quotation and its source line as one citation block. In Markdown, prefix every line of both parts with `>`. In Apple Notes, apply one native Block Quote style across the complete quotation-plus-source selection so the left quote bar covers both parts. This applies whether or not the quotation has a linked personal annotation.

## Highlight with linked annotation

```markdown
> 书中的真实原句。
> ——《书名》，作者，〈章节名〉

**你当时的想法**
> 真实的历史笔记。

**我的解释**
对这组材料的解释与回应。
```

## Highlight without linked annotation

Omit the historical-note section entirely. Do not announce that no note exists.

```markdown
> 书中的真实原句。
> ——《书名》，作者，〈章节名〉

**我的解释**
对这组材料的解释与回应。
```

## Personal note without a verified quotation

```markdown
**你当时在《书名》中写下**
> 真实的历史笔记。

**我的解释**
对这条历史笔记的解释与回应。
```

## Optional synthesis

When several distinct materials are present, optionally end with:

```markdown
**我的整体理解**
把所有相关材料放在一起后，对当前问题的直接回应。
```

## No relevant material

Use exactly this fallback instead of a weak or fabricated citation:

```text
我没有在你现有的微信读书划线和笔记中找到足以回应这段困惑的内容。
我不会为了完成格式而勉强引用关系很弱的句子。
```

Use `render_response.py` to produce consistent Markdown, Notes-safe HTML, verification plaintext, and verified `quote_blocks` metadata from structured JSON. Each material supplies only `record_id`, an optional exact `review_id`, and the agent's `explanation`. The renderer retrieves quotation, book, author, chapter, and historical-note text from the current local mirror and rejects arbitrary source text.

The renderer owns HTML generation. Do not ask the model to author or interpolate HTML. It escapes every text field as UTF-8-safe content and emits explicit `<div>` paragraphs. The structural invariant is:

```html
<blockquote>
  <div>书中的真实原句。</div>
  <div>——《书名》，作者，〈章节名〉</div>
</blockquote>
<div><strong>你当时的想法</strong></div>
<blockquote><div>真实的历史笔记。</div></blockquote>
<div><strong>我的解释</strong></div>
<div>解释正文。</div>
```

The source stays inside the same semantic quote block as the quotation. Historical notes use a separate quote block; explanations never inherit quote styling. Omit the historical-note section when there is no verified personal annotation.

`quote_blocks` contains the exact quotation-plus-source selections that must receive Apple Notes' native Block Quote paragraph style. HTML `<blockquote>` is semantic staging only: the Notes scripting bridge may flatten it, so its presence does not prove that the native quote bar exists.

Date lines never belong to `quote_blocks`. The pre-write Notes modification date labels original text once, and the local write date labels each generated response; both remain ordinary paragraphs outside citation styling. The original-text date is the first visible body paragraph. Preserve the Apple Note title through its separate title metadata; do not put the title ahead of the date inside the body as a workaround.
