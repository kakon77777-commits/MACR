from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

from macr_runtime.config import load_provider_configs
from macr_runtime.event_store import SqliteEventStore
from macr_runtime.errors import ProviderAdmissionBusyError
from macr_runtime.execution import DispatchOrigin
from macr_runtime.providers.glm import GlmFlashWorkerProvider
from macr_runtime.registry import ProviderRegistry
from macr_runtime.runtime import RuntimeServices
from macr_runtime.storage import StorageLayout
from macr_runtime.t1_dispatcher import T1Dispatcher
from macr_runtime.t1_manifest import load_t1_manifest
from macr_runtime.token_policy import t1_glm_live_policy


ROOT = Path(__file__).resolve().parents[2]


class StaticKeySource:
    def load(self):
        return "test-id.test-secret"

    def check_metadata(self):
        return None


class RecordingTransport:
    def __init__(
        self,
        database: Path,
        dispatcher_id: str,
        release_signal: Path,
    ) -> None:
        self.events = SqliteEventStore(database)
        self.dispatcher_id = dispatcher_id
        self.release_signal = release_signal

    def post_json(self, url, *, headers, payload, timeout_s):
        del url, headers, payload, timeout_s
        self.events.append_standalone(
            "mock.t1_transport_called",
            str(uuid.uuid4()),
            {"dispatcher_id": self.dispatcher_id},
        )
        deadline = time.monotonic() + 30
        while not self.release_signal.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("T1 transport release signal was not observed")
            time.sleep(0.001)
        return {
            "id": f"mock-{self.dispatcher_id}",
            "model": "glm-5.3-flash",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "multiprocess candidate",
                        "reasoning_content": "omitted",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
                "prompt_tokens_details": {"cached_tokens": 0},
                "completion_tokens_details": {"reasoning_tokens": 6},
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state_root")
    parser.add_argument("manifest")
    parser.add_argument("start_signal")
    parser.add_argument("ready_signal")
    parser.add_argument("dispatcher_id")
    args = parser.parse_args()

    state_root = Path(args.state_root)
    start_signal = Path(args.start_signal)
    ready_signal = Path(args.ready_signal)
    os.environ["MACR_STATE_ROOT"] = str(state_root)
    layout = StorageLayout(
        source_root=str(ROOT),
        state_root=str(state_root),
        codex_home_target=r"D:\AI_RESIDENCE\AI_Runtime\codex-home",
    )
    services = RuntimeServices.from_layout(layout)
    config = next(
        item
        for item in load_provider_configs(ROOT / "config" / "providers.json")
        if item.id == "glm_flash_worker"
    )
    provider = GlmFlashWorkerProvider(
        config,
        transport=RecordingTransport(
            services.events.path,
            args.dispatcher_id,
            state_root / "t1-transport-release.signal",
        ),
        environ=os.environ,
        key_source=StaticKeySource(),
        token_policy=t1_glm_live_policy(),
        admission_guard=services.provider_admission,
    )
    manifest = load_t1_manifest(args.manifest)
    dispatcher = T1Dispatcher(ProviderRegistry((provider,)), services)
    bundle = dispatcher.load_bundle(manifest)

    ready_signal.touch()
    deadline = time.monotonic() + 30
    while not start_signal.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("T1 worker start signal was not observed")
        time.sleep(0.001)

    try:
        result = dispatcher.run_one(
            manifest,
            bundle,
            args.dispatcher_id,
            DispatchOrigin("test-process", "process_id", str(os.getpid())),
            allow_network=True,
            allow_local=False,
        )
    except ProviderAdmissionBusyError:
        print(
            json.dumps(
                {"status": "provider_admission_busy"},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    print(
        json.dumps(
            {"status": "completed", "result": result.to_dict()},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
