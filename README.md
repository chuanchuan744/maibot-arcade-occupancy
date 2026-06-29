# 机厅人数登记

基于 MaiBot 插件系统的群聊排卡人数登记插件。群成员可以用简短指令登记某个机厅当前人数，也可以查询单店或全部机厅的排卡信息。

## 功能

- 多机厅配置，每个机厅可单独设置查询指令、登记指令、开店时间和闭店时间。
- 支持群聊白名单，只响应指定 QQ 群。
- 支持用户黑名单，可分别控制黑名单用户是否能查询或登记。
- 支持按用户单独限速，查询和登记限速可分别配置。
- 支持管理员清空单店或全部机厅数据。
- 支持自定义回复模板，可使用人数、登记人、QQ 号、更新时间等变量。
- 闭店后自动清空该机厅数据，闭店期间查询会返回闭店提示。

## 安装

1. 将本仓库放入 MaiBot 的 `plugins` 目录。
2. 确保目录中包含 `_manifest.json`、`plugin.py` 和 `config.toml`。
3. 在 MaiBot WebUI 中启用插件，或按你的部署方式重启 MaiBot。

## 基本用法

默认配置中：

- `xyj` 查询嘉定信业店人数。
- `xy4` 登记嘉定信业店当前人数为 4。
- `j` 查询全部机厅排卡信息。
- `清空xyj` 清空指定机厅数据，仅管理员可用。
- `清空全部` 清空全部机厅数据，仅管理员可用。

每个机厅的指令都可以在 `config.toml` 或 WebUI 中调整。例如：

```toml
[[arcades]]
name = "嘉定信业店"
enabled = true
query_aliases = ["xyj", "jdxy"]
update_aliases = ["xy"]
open_time = "10:00"
close_time = "22:00"
```

## 常用配置

`allowed_groups` 和 `admin_users` 默认为空，部署时请按自己的 QQ 群号和管理员 QQ 号填写。

```toml
[permissions]
allowed_groups = []
blocked_users = []
admin_users = []
block_query = false
block_update = true

[rate_limit]
enable_query_limit = false
enable_update_limit = true
query_cooldown_seconds = 10
update_cooldown_seconds = 10
scope = "per_user"
```

## 模板变量

回复模板支持以下变量：

- `{arcade_name}`：机厅名称。
- `{count}`：当前登记人数。
- `{user_name}`：登记人的 QQ 群名片或昵称。
- `{user_qq}`：登记人的 QQ 号。
- `{updated_time}`：更新时间，格式为 `HH:MM:SS`。
- `{remaining_seconds}`：限速剩余秒数。
- `{all_lines}`：全部机厅汇总行。

## 发布信息

作者：chuanchuan  
插件 ID：`chuanchuan744.arcade-occupancy`  
仓库地址：`https://github.com/chuanchuan744/maibot-arcade-occupancy`
