from pathlib import Path

from packaging.markers import Marker
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


def test_nginx_proxy_uses_docker_dns_and_preserves_request_uri() -> None:
    nginx = (ROOT / "datara-web" / "deploy" / "nginx.conf").read_text(encoding="utf-8")

    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in nginx
    assert "set $api_upstream http://datara-api:8000;" in nginx
    assert nginx.count("proxy_pass $api_upstream$request_uri;") == 2
    assert "proxy_pass http://datara-api:8000" not in nginx


def test_linux_x86_cryptography_wheel_has_portable_fallback() -> None:
    requirements = (ROOT / "datara-backend" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    cryptography = [line for line in requirements if line.startswith("cryptography")]

    assert len(cryptography) == 2
    wheel_requirement = next(line for line in cryptography if "manylinux_2_34_x86_64.whl" in line)
    fallback_requirement = next(line for line in cryptography if "manylinux_2_34_x86_64.whl" not in line)
    wheel_marker = Marker(wheel_requirement.split(";", 1)[1].strip())
    fallback_marker = Marker(fallback_requirement.split(";", 1)[1].strip())

    linux_x86 = {"sys_platform": "linux", "platform_machine": "x86_64"}
    linux_arm = {"sys_platform": "linux", "platform_machine": "aarch64"}
    windows_x86 = {"sys_platform": "win32", "platform_machine": "AMD64"}

    assert wheel_marker.evaluate(linux_x86)
    assert not fallback_marker.evaluate(linux_x86)
    assert not wheel_marker.evaluate(linux_arm)
    assert fallback_marker.evaluate(linux_arm)
    assert not wheel_marker.evaluate(windows_x86)
    assert fallback_marker.evaluate(windows_x86)
