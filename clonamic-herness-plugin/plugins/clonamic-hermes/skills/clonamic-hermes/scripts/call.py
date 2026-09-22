#!/usr/bin/env python3
"""Run one bounded named CLI request and emit one JSON result."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time


PROVIDER = json.loads(r'''{"arguments":["{cli_args}","--ignore-rules","-z","{prompt}","-t",""],"executable":"hermes","executor":"clonamic-hermes","prompt_transport":"argv"}''')
EXECUTOR = PROVIDER["executor"]
EXECUTABLE = PROVIDER["executable"]
DEFAULT_TIMEOUT = 120.0
MIN_TIMEOUT = 0.05
MAX_TIMEOUT = 600.0
ACTIVE_ENV = "CLONAMIC_EXECUTOR_ACTIVE"
CAPTURE_LIMIT = 65536
TRUNCATION_MARKER = "\n[output truncated]"
VALUE_FLAGS = frozenset({"--model", "-m", "--effort", "--reasoning-effort", "--output-format", "--format"})
SWITCH_FLAGS = frozenset({"--json"})
FORBIDDEN_FLAG_PARTS = ("permission", "sandbox", "tool", "bypass", "yolo", "approval", "dangerous")
VALUE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+:@-]*")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def timeout_value(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if not MIN_TIMEOUT <= value <= MAX_TIMEOUT:
        raise argparse.ArgumentTypeError(f"timeout must be between {MIN_TIMEOUT} and {MAX_TIMEOUT} seconds")
    return value


def parser() -> Parser:
    result = Parser(description=__doc__)
    result.add_argument("--timeout", type=timeout_value, default=DEFAULT_TIMEOUT)
    result.add_argument("--cli-arg", action="append", default=[])
    result.add_argument("prompt", nargs=argparse.REMAINDER)
    return result


def redact(text: str) -> str:
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer <redacted>", text)
    label = r"(?:[A-Za-z0-9]+_)*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|authorization)"
    text = re.sub(
        rf"(?im)\b({label})\b([ \t]*(?::|=|\bis\b)?[ \t]*)(\"[^\r\n\"]*\"|'[^\r\n']*'|[^\r\n]+)",
        r"\1\2<redacted>",
        text,
    )
    return re.sub(
        r"(?i)\b(?:sk-[A-Za-z0-9_-]{10,}|xai-[A-Za-z0-9_-]{10,}|gh[pousr]_[A-Za-z0-9_-]{10,}|github_pat_[A-Za-z0-9_-]{10,})\b",
        "<redacted>",
        text,
    )


def validate_cli_args(values: list[str]) -> list[str]:
    checked: list[str] = []
    index = 0
    while index < len(values):
        raw = values[index]
        folded = raw.casefold()
        if any(part in folded for part in FORBIDDEN_FLAG_PARTS):
            raise ValueError("unsafe CLI option")
        if raw in SWITCH_FLAGS:
            checked.append(raw)
            index += 1
            continue
        if "=" in raw:
            flag, value = raw.split("=", 1)
            if flag not in VALUE_FLAGS or not VALUE_PATTERN.fullmatch(value):
                raise ValueError("unsupported CLI option")
            checked.append(raw)
            index += 1
            continue
        if raw not in VALUE_FLAGS or index + 1 >= len(values):
            raise ValueError("unsupported CLI option")
        value = values[index + 1]
        if not VALUE_PATTERN.fullmatch(value):
            raise ValueError("invalid CLI option value")
        checked.extend((raw, value))
        index += 2
    return checked


class BoundedCapture:
    def __init__(self, stream) -> None:
        self.stream = stream
        self.data = bytearray()
        self.truncated = False

    def drain(self) -> None:
        try:
            while True:
                chunk = self.stream.read(8192)
                if not chunk:
                    return
                remaining = CAPTURE_LIMIT - len(self.data)
                if remaining > 0:
                    self.data.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self.truncated = True
        finally:
            self.stream.close()

    def text(self) -> str:
        value = self.data.decode("utf-8", errors="replace")
        return value + (TRUNCATION_MARKER if self.truncated else "")


def _write_stdin(stream, payload: bytes) -> None:
    try:
        stream.write(payload)
        stream.flush()
    except (BrokenPipeError, OSError):
        pass
    finally:
        stream.close()


def start_capture(
    proc: subprocess.Popen[bytes], prompt_input: bytes | None = None
) -> tuple[list[threading.Thread], BoundedCapture, BoundedCapture]:
    assert proc.stdout is not None and proc.stderr is not None
    stdout = BoundedCapture(proc.stdout)
    stderr = BoundedCapture(proc.stderr)
    threads = [threading.Thread(target=stdout.drain, daemon=True), threading.Thread(target=stderr.drain, daemon=True)]
    if prompt_input is not None:
        assert proc.stdin is not None
        threads.append(threading.Thread(target=_write_stdin, args=(proc.stdin, prompt_input), daemon=True))
    for thread in threads:
        thread.start()
    return threads, stdout, stderr


def finish_capture(threads: list[threading.Thread], stdout: BoundedCapture, stderr: BoundedCapture) -> tuple[str, str]:
    for thread in threads:
        thread.join(timeout=2)
    return stdout.text(), stderr.text()


def result(
    *,
    ok: bool,
    output: str = "",
    stderr: str = "",
    error: dict[str, str] | None = None,
    exit_code: int,
    timed_out: bool = False,
    duration_ms: int = 0,
) -> dict[str, object]:
    return {
        "ok": ok,
        "executor": EXECUTOR,
        "output": redact(output),
        "stderr": redact(stderr),
        "error": error,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms": duration_ms,
    }


def emit(payload: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return int(payload["exit_code"])


def _windows_job(proc: subprocess.Popen[bytes]):
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimit()
    limits.BasicLimitInformation.LimitFlags = 0x00002000
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel32.CloseHandle(job)
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(proc._handle)):
        kernel32.CloseHandle(job)
        raise ctypes.WinError(ctypes.get_last_error())
    return job


def cleanup_process_tree(proc: subprocess.Popen[bytes], job=None) -> None:
    if os.name == "nt":
        if job:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(job)
        elif proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    time.sleep(0.05)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def command(executable: str, cli_args: list[str], prompt: str, prompt_file: str | None) -> list[str]:
    output = [executable]
    for token in PROVIDER["arguments"]:
        if token == "{cli_args}":
            output.extend(cli_args)
        elif token == "{prompt}":
            output.append(prompt)
        elif token == "{prompt_file}":
            if prompt_file is None:
                raise ValueError("prompt file is required")
            output.append(prompt_file)
        else:
            output.append(token)
    return output


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    try:
        args = parser().parse_args(argv)
    except (ValueError, argparse.ArgumentTypeError) as exc:
        return emit(result(ok=False, error={"code": "usage", "message": str(exc)}, exit_code=2))

    if os.environ.get(ACTIVE_ENV):
        return emit(
            result(
                ok=False,
                error={"code": "recursion_blocked", "message": "an executor is already active"},
                exit_code=2,
            )
        )

    try:
        cli_args = validate_cli_args(args.cli_arg)
    except ValueError as exc:
        return emit(result(ok=False, error={"code": "cli_arg_rejected", "message": str(exc)}, exit_code=2))

    prompt_tokens = args.prompt[1:] if args.prompt[:1] == ["--"] else args.prompt
    prompt = " ".join(prompt_tokens).strip() or sys.stdin.read().strip()
    if not prompt:
        return emit(result(ok=False, error={"code": "usage", "message": "prompt is required"}, exit_code=2))

    executable = shutil.which(EXECUTABLE)
    if executable is None:
        return emit(
            result(
                ok=False,
                error={"code": "missing_cli", "message": f"{EXECUTABLE} is not available on PATH"},
                exit_code=127,
            )
        )

    env = os.environ.copy()
    env[ACTIVE_ENV] = EXECUTOR
    transport = PROVIDER.get("prompt_transport", "argv")
    prompt_file = None
    if transport == "file":
        descriptor, prompt_file = tempfile.mkstemp(prefix="clonamic-prompt-", suffix=".txt")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                if os.name == "posix":
                    os.chmod(prompt_file, 0o600)
                handle.write(prompt)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            os.unlink(prompt_file)
            raise
    try:
        proc = subprocess.Popen(
            command(executable, cli_args, prompt, prompt_file),
            stdin=subprocess.PIPE if transport == "stdin" else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=(os.name == "posix"),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except (OSError, ValueError) as exc:
        if prompt_file is not None:
            os.unlink(prompt_file)
        elapsed = int((time.monotonic() - started) * 1000)
        return emit(
            result(
                ok=False,
                error={"code": "spawn_error", "message": redact(str(exc))},
                exit_code=126,
                duration_ms=elapsed,
            )
        )

    job = None
    try:
        job = _windows_job(proc) if os.name == "nt" else None
    except BaseException as exc:
        cleanup_process_tree(proc)
        if prompt_file is not None:
            os.unlink(prompt_file)
        elapsed = int((time.monotonic() - started) * 1000)
        return emit(result(ok=False, error={"code": "spawn_error", "message": redact(str(exc))}, exit_code=126, duration_ms=elapsed))

    threads, stdout_capture, stderr_capture = start_capture(
        proc, prompt.encode("utf-8") if transport == "stdin" else None
    )
    timed_out = False
    interrupted = False
    try:
        proc.wait(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    except KeyboardInterrupt:
        interrupted = True
    finally:
        cleanup_process_tree(proc, job)
        if prompt_file is not None:
            try:
                os.unlink(prompt_file)
            except FileNotFoundError:
                pass

    stdout, stderr = finish_capture(threads, stdout_capture, stderr_capture)
    if timed_out:
        code = 124
        error = {"code": "timeout", "message": "executor timed out"}
    elif interrupted:
        code = 130
        error = {"code": "interrupted", "message": "executor interrupted"}
    else:
        return_code = proc.returncode if proc.returncode is not None else 1
        code = 128 - return_code if return_code < 0 else return_code
        error = None if code == 0 else {"code": "upstream_error", "message": redact(stderr.strip() or "executor failed")}
    elapsed = int((time.monotonic() - started) * 1000)
    return emit(
        result(
            ok=(code == 0),
            output=stdout,
            stderr=stderr,
            error=error,
            exit_code=code,
            timed_out=timed_out,
            duration_ms=elapsed,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
