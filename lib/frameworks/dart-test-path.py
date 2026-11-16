"""Resolve the already installed Dart test runner without invoking pub."""
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse


def test_entry(root=Path('.'), package='test'):
    config = (root / '.dart_tool/package_config.json').resolve()
    entries = [p for p in json.loads(config.read_text())['packages'] if p['name'] == package]
    if len(entries) != 1:
        raise ValueError('the existing package configuration must contain package:test')
    uri = urlparse(urljoin(config.as_uri(), entries[0]['rootUri']))
    if uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
        raise ValueError('package:test must already exist on the local filesystem')
    path = Path(unquote(uri.path)) / f'bin/{package}.dart'
    if not path.is_file():
        raise ValueError('package:test is not installed; no dependency was added')
    return path


if __name__ == '__main__':
    try:
        print(test_entry(package=sys.argv[1] if len(sys.argv) > 1 else 'test'))
    except (OSError, ValueError, KeyError) as error:
        sys.exit(str(error))
