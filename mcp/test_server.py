"""Tests for the MCP server. Run with: PYTHONPATH=.:../lib/layers python -m unittest test_server"""

import io
import json
import unittest

import server
from layers.config import parse

CATALOGUE = {
    "rust": {
        "description": "Rust development environment",
        "tools": [{"name": "cargo-nextest", "description": "Next-generation test runner"}],
        "quality": "when Cargo.toml cargo clippy\n",
        "style": "when Cargo.toml cargo fmt --all\n",
        "security": "when Cargo.lock cargo audit\n",
        "architecture": ["when deny.toml cargo deny check bans\n"],
        "tests": {"run": ["when Cargo.toml cargo nextest run\n"], "mutation": ["when Cargo.toml cargo mutants\n"]},
        "semgrep": True,
        "trivy": True,
        "nixpkgsConfig": [],
    },
    "hashi": {
        "description": "HashiCorp environment",
        "tools": [],
        "quality": "",
        "style": "",
        "security": "",
        "architecture": [],
        "tests": {},
        "semgrep": False,
        "trivy": False,
        "nixpkgsConfig": ["config.allowUnfree = true;"],
    },
}


def call(name: str, arguments: dict | None = None) -> tuple[bool, object]:
    reply = server.handle(CATALOGUE, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})
    result = reply["result"]
    text = result["content"][0]["text"]
    return result["isError"], (text if result["isError"] else json.loads(text))


class Protocol(unittest.TestCase):
    def test_initialize_keeps_a_version_it_knows_and_offers_its_own_otherwise(self):
        for asked, got in (("2024-11-05", "2024-11-05"), ("1999-01-01", server.PROTOCOLS[0])):
            reply = server.handle(CATALOGUE, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": asked}})
            self.assertEqual(reply["result"]["protocolVersion"], got)
            self.assertEqual(reply["result"]["capabilities"], {"tools": {}})
            self.assertIn("generate_flake", reply["result"]["instructions"])

    def test_a_notification_gets_no_reply(self):
        self.assertIsNone(server.handle(CATALOGUE, {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tools_are_listed_with_their_schemas(self):
        tools = server.handle(CATALOGUE, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["list_languages", "describe_language", "generate_flake", "architecture_rules"])
        self.assertTrue(all(t["inputSchema"]["type"] == "object" and t["description"] for t in tools))

    def test_unknown_methods_and_tools_are_errors(self):
        self.assertEqual(server.handle(CATALOGUE, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"})["error"]["code"], -32601)
        self.assertEqual(server.handle(CATALOGUE, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope"}})["error"]["code"], -32602)
        self.assertEqual(server.handle(CATALOGUE, {"jsonrpc": "2.0", "id": 5, "method": "ping"})["result"], {})

    def test_one_message_per_line_in_and_out(self):
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            "",
            "not json",
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps([{"jsonrpc": "2.0", "id": 7, "method": "ping"}, {"jsonrpc": "2.0", "id": 8, "method": "ping"}]),
        ]
        out = io.StringIO()
        server.serve(CATALOGUE, lines, out)
        replies = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(replies[0], {"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual(replies[1]["error"]["code"], -32700)
        self.assertEqual([r["id"] for r in replies[2]], [7, 8])
        self.assertEqual(len(replies), 3)


class Tools(unittest.TestCase):
    def test_list_languages(self):
        error, result = call("list_languages")
        self.assertFalse(error)
        self.assertEqual(
            result["languages"][1],
            {"name": "rust", "description": "Rust development environment", "architecture_reads": ["rust"], "architecture_tools": True, "tests": ["mutation", "run"]},
        )

    def test_describe_language_shows_what_each_command_runs(self):
        error, result = call("describe_language", {"name": "rust"})
        self.assertFalse(error)
        self.assertEqual(result["commands"]["tests --mutation"], "when Cargo.toml cargo mutants\n")
        self.assertIn("semgrep", result["commands"]["security"])
        self.assertEqual(result["tools"][0]["name"], "cargo-nextest")

    def test_an_unknown_language_is_an_error_with_a_suggestion(self):
        error, text = call("describe_language", {"name": "rst"})
        self.assertTrue(error)
        self.assertIn("Did you mean rust?", text)

    def test_generate_flake(self):
        error, result = call("generate_flake", {"languages": ["rust", "hashi"], "extra_tools": ["jq", "python3Packages.requests"], "checks": True})
        self.assertFalse(error)
        flake = result["files"]["flake.nix"]
        for expected in ('"rust"', '"hashi"', "config.allowUnfree = true;", "python3Packages.requests", "src = self;", "(project pkgs).checks", 'url = "github:nix-templates/dev";'):
            self.assertIn(expected, flake)
        self.assertEqual(flake.count("{"), flake.count("}"))
        self.assertEqual(result["commands"][-2:], ["tests", "tests --mutation"])
        self.assertIn("architecture_rules", result["next"][0])
        self.assertIn("use flake", result["files"][".envrc"])

    def test_generate_flake_refuses_what_it_cannot_write_safely(self):
        self.assertTrue(call("generate_flake", {"languages": []})[0])
        self.assertTrue(call("generate_flake", {"languages": ["rust"], "extra_tools": ["jq; rm -rf /"]})[0])
        self.assertTrue(call("generate_flake", {"languages": ["cobol"]})[0])

    def test_architecture_rules_writes_what_the_checker_reads(self):
        error, result = call(
            "architecture_rules",
            {"strict": True, "layers": [{"name": "core", "paths": ["src/core"], "pure": True}, {"name": "app", "paths": ["src"], "may_use": ["core"], "hint": 'Say "why".'}]},
        )
        self.assertFalse(error)
        config = parse(result["files"]["architecture.toml"])
        self.assertTrue(config.strict)
        self.assertEqual([(l.name, l.pure, l.may_use) for l in config.layers], [("core", True, []), ("app", False, ["core"])])
        self.assertEqual(config.layers[1].hint, 'Say "why".')

    def test_architecture_rules_writes_roots_and_purity(self):
        error, result = call(
            "architecture_rules",
            {"layers": [{"name": "core", "paths": ["src/core"], "pure": True}], "roots": ["code"], "purity_allow": ["time"], "purity_forbid": ["acme"]},
        )
        self.assertFalse(error)
        config = parse(result["files"]["architecture.toml"])
        self.assertEqual((config.roots, config.purity_allow, config.purity_forbid), (["code"], ["time"], ["acme"]))

    def test_architecture_rules_refuses_rules_the_checker_would_refuse(self):
        error, text = call("architecture_rules", {"layers": [{"name": "core", "paths": ["src"], "may_use": ["nowhere"]}]})
        self.assertTrue(error)
        self.assertIn("not a layer", text)
        self.assertTrue(call("architecture_rules", {"layers": [{"name": "core", "paths": ["src"], "colour": "red"}]})[0])

    def test_architecture_rules_without_layers_explains_the_format(self):
        error, result = call("architecture_rules")
        self.assertFalse(error)
        self.assertIn("functional core", result["reference"])
        for language in ("rust", "go", "java", "qml", "shell"):
            self.assertIn(language, result["reference"])
        self.assertFalse(call("architecture_rules", result["example_arguments"])[0])


if __name__ == "__main__":
    unittest.main()
