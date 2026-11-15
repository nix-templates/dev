"""What a pure layer may not touch, per language.

A pure layer is a functional core: the same input gives the same output, and
nothing outside the function changes. So no files, network, processes, clock,
environment, randomness, threads or shared mutable state. An entry matches a
package or any path below it ("std::fs" matches "std::fs::read").

architecture.toml adds to these lists with [purity] forbid and takes from them
with [purity] allow.
"""

RUST = (
    # the outside world
    "std::fs",
    "std::net",
    "std::process",
    "std::env",
    "std::os",
    "std::thread",
    "std::io::stdin",
    "std::io::stdout",
    "std::io::stderr",
    # shared mutable state
    "std::sync::Mutex",
    "std::sync::RwLock",
    "std::sync::Condvar",
    "std::sync::OnceLock",
    "std::sync::LazyLock",
    "std::sync::atomic",
    "std::sync::mpsc",
    "std::cell",
    "core::cell",
    "core::sync::atomic",
    # runtimes, I/O, databases, randomness and system calls
    "tokio",
    "async_std",
    "smol",
    "mio",
    "futures",
    "reqwest",
    "hyper",
    "ureq",
    "zbus",
    "dbus",
    "rusqlite",
    "sqlx",
    "postgres",
    "tokio_postgres",
    "rand",
    "getrandom",
    "fastrand",
    "libc",
    "nix",
    "rustix",
    "notify",
    "inotify",
    "once_cell",
    "lazy_static",
    "parking_lot",
)

PYTHON = (
    "os",
    "sys",
    "subprocess",
    "socket",
    "ssl",
    "select",
    "selectors",
    "signal",
    "http",
    "urllib.request",
    "ftplib",
    "smtplib",
    "requests",
    "httpx",
    "aiohttp",
    "websockets",
    "sqlite3",
    "dbm",
    "shelve",
    "shutil",
    "tempfile",
    "glob",
    "pathlib",
    "io",
    "time",
    "random",
    "secrets",
    "threading",
    "multiprocessing",
    "concurrent",
    "asyncio",
    "logging",
    "ctypes",
)

# Parts of a forbidden module that have no side effects.
PYTHON_ALLOWED = (
    "pathlib.PurePath",
    "pathlib.PurePosixPath",
    "pathlib.PureWindowsPath",
    "io.StringIO",
    "io.BytesIO",
    "os.path",
    "os.PathLike",
    "os.fspath",
)

JAVASCRIPT = (
    "fs",
    "child_process",
    "net",
    "http",
    "https",
    "http2",
    "dgram",
    "dns",
    "os",
    "process",
    "readline",
    "tty",
    "cluster",
    "worker_threads",
    "axios",
    "node-fetch",
    "undici",
    "ws",
)

CPP = (
    "fstream",
    "iostream",
    "cstdio",
    "stdio.h",
    "filesystem",
    "thread",
    "mutex",
    "shared_mutex",
    "atomic",
    "condition_variable",
    "future",
    "random",
    "ctime",
    "time.h",
    "chrono",
    "unistd.h",
    "fcntl.h",
    "sys",
    "pthread.h",
    "QFile",
    "QDir",
    "QProcess",
    "QTimer",
    "QThread",
    "QSettings",
    "QtNetwork",
    "QtDBus",
    "QtSql",
)

SEPARATORS = ("::", ".", "/")


def language_of(path: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    if name.endswith(".rs") or name == "Cargo.toml":
        return "rust"
    if name.endswith(".py"):
        return "python"
    if name.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")):
        return "javascript"
    if name.endswith((".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx")):
        return "cpp"
    return None


DEFAULTS = {"rust": RUST, "python": PYTHON, "javascript": JAVASCRIPT, "cpp": CPP}
ALLOWED = {"python": PYTHON_ALLOWED}


def covers(entry: str, package: str, path: str) -> bool:
    """True when entry names the package, the path, or something above the path."""
    if entry in (package, path):
        return True
    return any(path.startswith(entry + separator) for separator in SEPARATORS)


def first_covering(entries, package: str, path: str) -> str | None:
    for entry in entries:
        if covers(entry, package, path):
            return entry
    return None
