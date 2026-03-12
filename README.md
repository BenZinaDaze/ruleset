# 前言
#### 将 `domain`格式的ruleset转为小火箭支持的`classical`格式

# 使用说明

## 本地运行

单个文件转换：

```bash
python3 convert_rule_list.py -i ai.list
python3 convert_rule_list.py -i "https://example.com/test.list"
```

按配置文件批量转换：

```bash
python3 convert_rule_list.py -c rule.yaml
```

## `rule.yaml` 规则

格式如下：

```yaml
rules:
  name: mihomo-ruleset
  url:
    - "https://example.com/a.list"
    - "https://example.com/b.list"
```

说明：

- `rules.name`：GitHub Release 的名称
- `rules.url`：需要转换的来源地址列表

转换规则：

- 以 `+.` 开头的行会转成 `DOMAIN-SUFFIX`
- 以 `#` 开头的行会忽略
- 其他非空行会转成 `DOMAIN`

## 自动发布

提交并 push 修改后的 [rule.yaml](/home/benz1/Code/github/ruleset/rule.yaml) 到 `main` 分支后，会自动触发 GitHub Actions 发布。

### GitHub Actions 也会每两小时自动运行一次。

发布时会：

- 读取 `rule.yaml`
- 使用 `rules.name` 作为 Release 名称
- 下载并转换 `rules.url` 中的所有地址
- 将生成的 `.list` 文件上传到对应 Release 的 Assets

# 欢迎提交 PR 和 Issue。
