"""Generate the TypeScript wire contract from the API's own OpenAPI schema.

The point is not convenience. Two clients hand-maintaining their own idea of an
``Assessment`` is how a mobile app starts rendering a field the server stopped sending —
silently, because nothing fails until a user looks at it. Generating from the server means
the check happens at compile time, in every client, on every build (D33).

Deliberately a small generator rather than a code-generation toolchain: the schema this
API produces is flat, and one readable file beats a dependency whose output nobody reads.
It handles exactly what ``api/schemas.py`` uses — objects, arrays, string literal unions,
nullable fields and references — and *fails loudly* on anything else rather than emitting
``any``. An ``any`` in a generated contract is a contract that stopped being checked.

Run with ``make api-types``. The output is committed, so a clone builds without a running
server and a diff of it is a visible change to the promise made to clients.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

BANNER = """/**
 * GENERATED — do not edit.
 *
 * The wire contract, produced from the backend's OpenAPI schema by
 * `packages/backend/scripts/generate_api_types.py` (`make api-types`).
 *
 * Every client renders these verdicts; none of them computes one. Attention, confidence,
 * coverage, corroboration, canonical order and contradiction state all arrive decided.
 *
 * API version: {version}
 */

"""


class Unsupported(Exception):
    """A schema construct this generator will not guess at."""


def type_of(schema: dict[str, Any], name: str) -> str:
    """One JSON-schema node as a TypeScript type."""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]

    if "anyOf" in schema:
        return " | ".join(type_of(option, name) for option in schema["anyOf"])
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return type_of(schema["allOf"][0], name)

    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])

    kind = schema.get("type")
    if kind == "array":
        return f"{type_of(schema.get('items', {}), name)}[]"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if extra in (True, None):
            return "Record<string, unknown>"
        return f"Record<string, {type_of(extra, name)}>"
    simple = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean"}
    if kind in simple:
        return simple[kind]
    if kind == "null":
        return "null"
    if not schema:
        # An untyped node would become `any`, which is how a generated contract quietly
        # stops being a contract. Refuse instead.
        raise Unsupported(f"{name}: an untyped schema node cannot be generated safely")
    raise Unsupported(f"{name}: unsupported schema {json.dumps(schema)[:120]}")


def render(name: str, schema: dict[str, Any]) -> str:
    """One component schema as an exported interface."""
    if "enum" in schema and "properties" not in schema:
        return f"export type {name} = {type_of(schema, name)};\n"

    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for field, definition in schema.get("properties", {}).items():
        description = definition.get("description", "").strip()
        if description:
            lines.append("  /** " + " ".join(description.split()) + " */")
        optional = "" if field in required else "?"
        lines.append(f"  {field}{optional}: {type_of(definition, f'{name}.{field}')};")
    lines.append("}\n")
    return "\n".join(lines)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate or verify the shared API contract.")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("../shared/src/api.generated.ts"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed generated contract differs from the current OpenAPI schema.",
    )
    return parser.parse_args()


def main() -> int:
    options = arguments()
    api_version, document = _openapi()
    components = document.get("components", {}).get("schemas", {})
    if not components:
        print("no component schemas: are response models attached to the routes?")
        return 1

    body = [BANNER.format(version=api_version)]
    body.append(f'export const API_VERSION = "{api_version}";\n')
    body.append(f'export const API_PREFIX = "/{api_version}";\n')
    for name in sorted(components):
        # Validation-error shapes are FastAPI's, not this product's contract.
        if name in ("HTTPValidationError", "ValidationError"):
            continue
        body.append(render(name, components[name]))

    rendered = _format("\n".join(body))
    out = options.output
    if options.check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != rendered:
            print(f"generated API contract is stale: run make api-types ({out})")
            return 1
        print(f"generated API contract is current ({out})")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")

    print(f"wrote {out} ({len(components)} schemas)")
    return 0


def _format(rendered: str) -> str:
    """Apply the clients' formatter before writing or drift-checking."""
    result = subprocess.run(
        ["bun", "run", "prettier", "--stdin-filepath", "api.generated.ts"],
        cwd=Path(__file__).resolve().parents[2] / "web",
        check=True,
        capture_output=True,
        input=rendered,
        text=True,
    )
    return result.stdout


def _openapi() -> tuple[str, dict[str, Any]]:
    """Load the application schema against disposable state, never a working database."""
    with tempfile.TemporaryDirectory(prefix="watchlist-contract-") as directory:
        os.environ["WATCHLIST_DB"] = str(Path(directory) / "contract.db")
        os.environ["INGEST_SCHEDULER"] = "off"
        from smart_watchlist.api.app import API_VERSION, app

        return API_VERSION, app.openapi()


if __name__ == "__main__":
    raise SystemExit(main())
