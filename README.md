# 订阅收入月桥

订阅收入分析员可在工作台上传来源 CSV，对照规则判断差异，并按业务组逐组签发或记录暂缓意见。对账相符的组可独立签发；跨组冲突牵涉的组与无法归组坏行所在的整批按规则暂缓。

按月初月末及月内事件拆分新增、扩张、收缩和流失。

## 启动

```sh
docker compose up --build -d --wait
```

打开 <http://localhost:18302>。页面预览带异常样例。选中阶段查看计算证据，执行批次后在结果表选择业务组，填写复核意见并「签发该组」或「暂缓该组」，再下载逐组复核证据。

## 核验

```sh
docker compose exec -T app pytest -q
```

[输入字段](docs/DATA-DICTIONARY.md) · [阶段接口](docs/HTTP.md) · [操作步骤](docs/OPERATIONS.md) · [规则与测试](docs/DEPTH.md)
