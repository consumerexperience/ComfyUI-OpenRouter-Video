"""Package-level scaffold checks."""

from pathlib import Path

import openrouter_video


def test_package_is_importable_and_exports_no_product_api() -> None:
    assert openrouter_video.__all__ == ()


def test_required_module_seams_exist() -> None:
    package_root = Path(openrouter_video.__file__).parent
    expected = {
        "application.py",
        "models.py",
        "lifecycle.py",
        "capabilities.py",
        "client.py",
        "request_policy.py",
        "app_identity.py",
        "transport.py",
        "persistence.py",
        "media.py",
        "secrets.py",
        "errors.py",
        "observability.py",
        "policy.py",
    }
    assert expected <= {path.name for path in package_root.glob("*.py")}
