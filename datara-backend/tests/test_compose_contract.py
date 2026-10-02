from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_kafka_is_a_persistent_healthy_default_service() -> None:
    compose = _compose()
    kafka = compose["services"]["kafka"]
    assert kafka["container_name"] == "datara-kafka"
    assert kafka["environment"]["KAFKA_CFG_ADVERTISED_LISTENERS"] == "PLAINTEXT://datara-kafka:9092"
    assert "kafka-data:/bitnami/kafka" in kafka["volumes"]
    assert "healthcheck" in kafka
    assert "kafka-data" in compose["volumes"]


def test_worker_waits_for_kafka_and_uses_validated_address() -> None:
    compose = _compose()
    assert compose["services"]["datara-worker"]["depends_on"]["kafka"]["condition"] == "service_healthy"
    assert compose["x-backend-env"]["KAFKA_BOOTSTRAP_SERVERS"] == "datara-kafka:9092"
