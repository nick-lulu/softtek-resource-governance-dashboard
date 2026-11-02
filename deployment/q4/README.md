# Q4 Planning · 阿里云服务器部署包

这份包来自现有 GitHub Q4 Planning 的同一批公开页面，不连接 Confluence API，不包含 Excel 原件、API Token、SSH 凭证或合同 Settlement 页面。保持现有公开访问方式；如果改为内部访问或公司 SSO，部署前按确定的方案加访问控制。

## 页面入口

根目录 `/` 打开 `/summary/`。其他入口：

| 地址 | 内容 |
| --- | --- |
| `/summary/` | Total Summary |
| `/resources/` | Resource List |
| `/corporate/` | Corporate |
| `/upstream-scm-mdm/` | Upstream SCM & MDM |
| `/mpa/` | MP&A |
| `/fulfillment/` | Fulfillment |
| `/qa/` | 所有 domain 的 QA 汇总 |
| `/q4-ops/` | SCM Ops |
| `/q4-ops-plan-b/` | Plan B |
| `/project-labels/` | Project Labels |

无需服务器 Node.js 或前端编译。静态页面中的相对链接及跨域资源汇总均保持原逻辑，文件必须整体部署。表格数据为快照；网页内的个人本地草稿不会自动写回 GitHub，Timesheet Actual 仍维持现有连接状态。

## 明天部署前需要的信息

- 服务器公网 IP、Linux 系统及 CPU 架构、SSH 用户/可用登录方式。
- 域名及 DNS 管理权限；是否已有其他网站占用 80/443 端口。
- 访问范围：沿用公开访问、公司网络，或需要登录。
- Docker / Compose 是否已安装。未安装时按实际服务器系统安装，或采用现有 Nginx。

凭证通过受支持的授权连接提供，不写入此包或 GitHub。

## 方式 A：上传压缩包直接运行

前提：Linux、Docker Engine、Docker Compose v2（支持 `up --wait`）。先把 zip 上传到服务器，并校验同目录 SHA256SUMS.txt。

```sh
sha256sum -c SHA256SUMS.txt
unzip Q4-Planning-Aliyun-Ready.zip
cd q4-planning-server
cp .env.example .env
sh deploy.sh
```

初次使用 `SITE_ADDRESS=:80`，访问 `http://服务器IP/`。若 80/443 已被其他服务占用，先处理现有站点或改用 Nginx 方式，不能直接启动第二个监听同端口的服务。

## 绑定域名和 HTTPS

1. 域名 A 记录指向服务器公网 IPv4；没有 IPv6 时不要添加 AAAA 记录。
2. 阿里云安全组和服务器防火墙允许网站所需的 TCP 80/443；SSH 按管理员实际访问来源配置。
3. 将 `.env` 的 `SITE_ADDRESS` 改为实际域名，例如 `planning.example.com`，不加 `https://`，也不加路径。
4. 再执行 `sh deploy.sh`。DNS、端口及证书签发条件满足时，Caddy 自动申请并续期 HTTPS 证书。
5. 执行：

```sh
python3 check.py https://planning.example.com
docker compose ps
docker compose logs --tail=100 dashboard
```

`check.py` 会核对实际服务器文件与 manifest.json 的 SHA256，验证所有看板、标签资源、数据快照和根入口。只有外部地址也通过检查，才算完成部署。不要使用 `docker compose down -v`，以免删除证书数据。

官方参考：[Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)、[阿里云网站安全组配置](https://help.aliyun.com/en/ecs/user-guide/security-groups-for-different-use-cases)。

## 方式 B：从 GitHub 获取最新代码后打包

```sh
git clone https://github.com/nick-lulu/softtek-resource-governance-dashboard.git q4-source
cd q4-source
python3 deployment/q4/package.py --output ../q4-release --revision "$(git rev-parse HEAD)"
cd ../q4-release/q4-planning-server
cp .env.example .env
sh deploy.sh
```

输出目录必须不存在，防止把其他文件误打包。以后在源目录 `git pull --ff-only` 后，用新的输出目录重新打包。保留旧版本目录和 `.env`。若新版本检查失败，可从旧版本目录执行 `sh deploy.sh` 恢复；数据为静态快照，不涉及数据库迁移。

GitHub Actions 的 **Build Q4 Server Package** 工作流也会从当前 main 构建并保存 `q4-planning-server` artifact，可从 Actions 下载。它不会登录或自动修改阿里云服务器。

## 已有 Nginx 的服务器

把 `site/` 整体放到独立目录，并参考 `nginx.conf.example` 新增站点。不要覆盖其他站点配置。调整 `root`、`server_name`，通过 `nginx -t` 后再 reload；HTTPS 使用现有证书管理方式。此方式不运行 Caddy 容器。

## 交付和验收边界

- 本地打包验证：JSON、内部页面/资源链接、文件完整性、资源数值类型、页面脚本语法；发布版本写入 manifest.json。
- 服务器到位后验证：容器配置、端口、DNS、证书、公开地址文件哈希、浏览器项目明细、Total Summary 和 Resource List 汇总。
- 当前尚无服务器连接，不能提前确认实际阿里云部署或 HTTPS 已成功。部署时按服务器实况完成以上检查。

## Summary 首屏加载优化

发布前运行 node deployment/q4/build-portfolio-snapshot.mjs，使用现有 Summary 的同一套计算函数，从当前 domain、Finance 和最终 QA 数据生成内嵌快照及 public/assets/portfolio-data.json。GitHub Pages 工作流和服务器打包脚本均自动运行此步骤；打包环境需安装 Node.js 22 及 Python 3。

Summary 首屏直接读取同版本快照，不再下载其他 domain 的完整 HTML。手动 Refresh 读取最新 JSON；快照缺失或无效时回退原来源页面。标签使用同版本内嵌数据，仅增强新增 DOM，筛选与明细无需反复扫描整个页面。所有源项目与人员计算口径保持不变。

Resource List 和 QA 也使用发布时生成的独立快照。Resource List 保留全部人员、未分类人员和原表 Allocated/Remaining 来源明细，并用引用消除与人员计划重复的项目记录；QA 快照保留最终 QA 预测与 QA Lead。所有 domain 内嵌同版本标签，并预加载共用脚本。人员表格、角色表和 Kanban 按当前视图生成，切换视图与导出功能保留。