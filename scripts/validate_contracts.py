import json
from pathlib import Path

import jsonschema
import yaml
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main():
    system = read_yaml(ROOT / "system.yaml")
    schema = json.loads((ROOT / "system.schema.json").read_bytes())
    jsonschema.validate(system, schema)

    services = system["services"]
    specifications = {}
    for name, service in services.items():
        spec = read_yaml(ROOT / service["openapi"])
        validate(spec)
        specifications[name] = spec
        if "get" not in spec["paths"].get(service.get("health", "/health"), {}):
            raise ValueError(f"{name} is missing its health endpoint")
        if not (ROOT / service["migrations"]).is_dir():
            raise ValueError(f"{name} is missing its migration directory")

    if not set(system["ui"]["calls"]) <= services.keys():
        raise ValueError("The UI calls an unknown service")
    for name, service in services.items():
        for call in service.get("calls", []):
            if call["url_env"] not in service["env"]:
                raise ValueError(f"{name} is missing the URL setting for a service call")
            paths = specifications[call["service"]]["paths"]
            for endpoint in call["endpoints"]:
                method, path = endpoint.split(" ", 1)
                if method.lower() not in paths.get(path, {}):
                    raise ValueError(f"{name} calls an undocumented endpoint: {endpoint}")
    print("Assignment system schema and both OpenAPI contracts are valid.")


if __name__ == "__main__":
    main()
