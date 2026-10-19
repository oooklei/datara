"""R6 P0 cross-process fencing and attempt dispatch protocol tests."""

from __future__ import annotations

from threading import Barrier, Lock, Thread

import pytest

from common import queue


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.outbox = {}
        self.streams = []
        self.lock = Lock()
        self.crash_after_commit = False

    def incr(self, key):
        with self.lock:
            self.values[key] = int(self.values.get(key, 0)) + 1
            return self.values[key]

    def eval(self, _script, key_count, *args):
        fence_key, outbox_key, stream = args[:key_count]
        token, dispatch_key, payload, digest = args[key_count:]
        with self.lock:
            current = int(self.values.get(fence_key, 0))
            if int(token) != current:
                raise queue.StaleMasterFence("stale leader fence")
            existing = self.outbox.get((outbox_key, dispatch_key))
            if existing:
                if existing[1] != digest:
                    raise queue.DispatchPayloadConflict("attempt payload changed")
                return existing[0]
            msg_id = f"{len(self.streams) + 1}-0"
            self.streams.append((stream, msg_id, payload))
            self.outbox[(outbox_key, dispatch_key)] = (msg_id, digest)
            crash = self.crash_after_commit
            self.crash_after_commit = False
        if crash:
            raise RuntimeError("injected crash after atomic enqueue")
        return msg_id


def _payload(attempt=3):
    return {"instanceId": "run-1", "taskId": 42, "attempt": attempt, "param": {"value": "stable"}}


def test_stale_leader_fence_cannot_dispatch_after_new_leader_claim(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(queue, "get_client", lambda: client)
    old = queue.claim_master_fence()
    new = queue.claim_master_fence()

    with pytest.raises(queue.StaleMasterFence):
        queue.add_task_fenced(_payload(), priority=3, fence_token=old)
    queue.add_task_fenced(_payload(), priority=3, fence_token=new)

    assert len(client.streams) == 1


def test_concurrent_leaders_produce_one_attempt_message(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(queue, "get_client", lambda: client)
    old = queue.claim_master_fence()
    new = queue.claim_master_fence()
    barrier = Barrier(3)
    outcomes = []

    def dispatch(token):
        barrier.wait()
        try:
            outcomes.append(queue.add_task_fenced(_payload(), priority=3, fence_token=token))
        except queue.StaleMasterFence:
            outcomes.append("stale")

    workers = [Thread(target=dispatch, args=(token,)) for token in (old, new)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=2)

    assert all(not worker.is_alive() for worker in workers)
    assert outcomes.count("stale") == 1
    assert len(client.streams) == 1


def test_replay_after_crash_between_enqueue_and_ack_returns_same_message(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(queue, "get_client", lambda: client)
    fence = queue.claim_master_fence()
    client.crash_after_commit = True

    with pytest.raises(RuntimeError, match="injected crash"):
        queue.add_task_fenced(_payload(), priority=3, fence_token=fence)
    replayed = queue.add_task_fenced(_payload(), priority=3, fence_token=fence)

    assert replayed == "1-0"
    assert len(client.streams) == 1


def test_same_attempt_key_rejects_changed_payload(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(queue, "get_client", lambda: client)
    fence = queue.claim_master_fence()
    queue.add_task_fenced(_payload(), priority=3, fence_token=fence)

    with pytest.raises(queue.DispatchPayloadConflict):
        queue.add_task_fenced({**_payload(), "param": {"value": "changed"}}, priority=3, fence_token=fence)

    assert len(client.streams) == 1
