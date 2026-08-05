# Reading Mirror

Reading Mirror 是一个面向 macOS Codex 的个人阅读回应 Skill。它读取用户明确指定的 Apple 备忘录，从用户自己的微信读书划线与笔记中检索相关材料，生成回应，并安全写回原备忘录。

## 主要能力

- 通过 Note ID、准确标题或用户提供的连续原文定位 Apple 备忘录。
- 唯一命中时直接回填；多条命中时只展示元数据并请用户确认。
- 使用已安装的 `weread-skills` 同步用户自己的微信读书划线和笔记。
- 校验引用来源，避免把模型生成文本当成书中原句。
- 支持多个 `（用我读过的书回答）` 标记及无标记追加模式。
- 写入前检查密码保护、共享状态、附件和并发修改。
- 通过 Apple Notes 原生 Block Quote 样式展示引用。

## 环境要求

- macOS 与 Apple Notes
- Codex
- Python 3
- [ripgrep](https://github.com/BurntSushi/ripgrep)
- 已安装并启用的 `weread-skills`
- 按 `weread-skills` 当前说明配置的 `WEREAD_API_KEY`

Reading Mirror 不包含、替代或绕过微信读书数据访问 Skill。若 `weread-skills` 未安装或未在当前 Codex 会话中启用，工作流会停止并提示用户处理依赖。

## 安装

```bash
git clone https://github.com/ysqqqq37/reading-mirror.git ~/.codex/skills/reading-mirror
```

重新打开 Codex 会话后，确认 Available Skills 中同时包含 `reading-mirror` 和 `weread-skills`。

## 使用

可以直接指定备忘录标题：

```text
使用 Reading Mirror 回答 Apple 备忘录《我的困惑》
```

也可以在备忘录正文中放置：

```text
（用我读过的书回答）
```

如果只向 Codex 提供一段备忘录原文，Reading Mirror 只进行本机连续文本精确匹配，不做语义或模糊扫描。唯一命中时直接回填；多条命中时会先让用户选择。

## 数据存储

Skill 代码与个人数据分开存放。默认运行数据目录为：

```text
~/Library/Application Support/Codex/reading-mirror/
├── mirror/
└── state/
```

用户可以通过 `READING_MIRROR_HOME` 指定其他位置。不要把运行数据目录提交到公开仓库。完整说明见 [PRIVACY.md](PRIVACY.md)。

## Apple Notes 权限

第一次使用时，macOS 可能要求调用方控制 Notes。允许后，脚本才能读取和写入用户指定的备忘录。原生引用块需要通过 Notes 编辑器应用段落样式，因此还可能需要相应的界面自动化权限。

## 第三方代码

Apple Notes 基础脚本来自 `lishix520/apple-notes-skill`；富文本转换设计参考 `midboss1028-beep/apple-notes-richtext-skill`。两者均为 MIT License，版权与许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 `licenses/`。

## License

Reading Mirror 自有代码以 MIT License 发布，见 [LICENSE](LICENSE)。第三方组件继续适用各自的许可证。
