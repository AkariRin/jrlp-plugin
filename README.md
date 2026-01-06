# 今日老婆插件 (JRLP Plugin)

🎲每天在群里随机抽取一位群友作为你的"群老婆"，每日限抽一次，结果当天有效。

## 触发命令

群内发送`抽老婆`、`今日老婆`、`jrlp`即可抽取

## 配置说明

插件配置文件位于 `config.toml`：

```toml
[plugin]
name = "jrlp_plugin"      # 插件名称
version = "1.0.0"         # 插件版本
enabled = true            # 是否启用插件
config_version = "1.0.0"  # 配置版本

[napcat]
address = "napcat"        # napcat服务器连接地址
port = 3000               # napcat服务器端口
```

### 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `napcat.address` | string | `"napcat"` | napcat 服务器地址，可以是 IP 或域名 |
| `napcat.port` | int | `3000` | napcat 服务器 HTTP API 端口 |

## 注意事项

- ⚠️ 该命令仅支持**群聊**环境，私聊无法使用
- 📍 抽取结果按群隔离，不同群的抽取互不影响
- 🔄 每天凌晨 0 点后可重新抽取
- 🚫 不会抽到自己

## 数据存储

插件数据存储在 `jrlp.db` SQLite 数据库
