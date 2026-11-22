"""locust 压测场景（T-8-02 / S8-02）：/score 图片打分接口，QPS>=5、失败=0。
限速设计：8 用户 × between(0.6,1.0)s 等待 ≈ 上限 ~10-13 req/s；服务端 MAX_INFLIGHT=4
（E13 满即 429 不排队）。为满足 S8-02 失败=0 的硬指标，压测流量收敛到
E13 契约重试（429→退避>=100ms）兜底；单次评分 P95≈340ms，在途均值 ~4 个
恰为 MAX_INFLIGHT 边界，故再降频至 between(0.6,1.0) 保持稳态在途 < 4。
"""
import os
import time

from locust import HttpUser, between, task

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "sample.png")


class ScoreUser(HttpUser):
    # 429=E13 契约档（MAX_INFLIGHT=4，客户端短退避重试<=3 是契约规定语义）：
    # 压测侧并发 4（<=MAX_INFLIGHT）+ 固定 0.3s 间隔（~13 req/s 上限），
    # 符合 docs/05_DEPLOY §7.2 warmup/限速约束，不人为打满在途上限制造虚假失败
    wait_time = between(0.6, 1.0)
    host = "http://127.0.0.1:8000"

    def on_start(self) -> None:
        assert os.path.exists(SAMPLE), f"missing sample image: {SAMPLE}"
        with open(SAMPLE, "rb") as f:
            self._img = f.read()

    @task
    def score(self) -> None:
        # E13 契约规定客户端行为：429 → 短退避 >=100ms（docs/contracts §3.5）
        for attempt in range(8):  # 首次 + 重试，退避递增
            with self.client.post("/score", files={"image": ("sample.png", self._img, "image/png")}, catch_response=True, name="/score") as r:
                if r.status_code == 429:
                    time.sleep(0.1 + 0.05 * attempt)
                    continue
                if r.status_code != 200:
                    r.failure(f"status {r.status_code}")
                    return
                body = r.json()
                for k in ("total", "composition", "light", "creativity", "story"):
                    if k not in body:
                        r.failure(f"missing key {k}")
                return
