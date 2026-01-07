# 今日老婆

🎲每天在群里随机抽取一位群友作为你的"群老婆"，每日限抽一次，结果当天有效。

## 触发命令

群内发送`抽老婆`、`今日老婆`、`jrlp`即可抽取

## 配置说明

插件配置文件位于 `config.toml`：

```toml
[plugin]
name = "jrlp-plugin"       # 插件名称
enabled = true             # 是否启用插件
config_version = "1.1.0"   # 配置版本

[napcat]
address = "napcat"         # napcat服务器连接地址
port = 3000                # napcat服务器端口

[messages]
# 已抽取老婆时的提示文本
# 支持占位符: {wife_name} 老婆昵称, {wife_qq} 老婆QQ号
already_rolled_text = "你今天已经有群老婆{wife_name}({wife_qq})了，要好好对待她哦~"

# 新抽取老婆时的提示文本
# 支持占位符: {wife_name} 老婆昵称, {wife_qq} 老婆QQ号
new_roll_text = "你今天的群老婆是:{wife_name}({wife_qq})"
```

## 注意事项

- ⚠️ 该命令仅支持**群聊**环境，私聊无法使用
- 📍 抽取结果按群隔离，不同群的抽取互不影响
- 🔄 每天凌晨 0 点后可重新抽取
- 🚫 不会抽到自己

## 数据存储

插件数据存储在 `jrlp.db` SQLite 数据库
