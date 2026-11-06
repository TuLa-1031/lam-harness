import asyncio
import posixpath
import time
from pathlib import PurePath
from typing import Any

import modal
from swerex.deployment.modal import ModalDeployment
from swerex.runtime.abstract import Command
from swerex.runtime.remote import RemoteRuntime

def _tls_port_config(
    modal_sandbox_kwargs: dict[str, Any],
    runtime_port: int
) -> tuple[list[int], list[int], dict[str, Any]]:
    """Put the control port on the TLS tunnel exaclty once."""

    kwargs = dict(modal_sandbox_kwargs)
    encrypted = list(kwargs.pop("encrypted_ports", []))
    unencrypted = [
        port for port in kwargs.pop("unecrypted_ports", []) if port != runtime_port
    ]
    encrypted = list(dict.fromkeys([runtime_port, *encrypted]))
    return encrypted, unencrypted, kwargs


class AssignmentModelDeployment(ModalDeployment):
    async def start(self) -> None:
        if self._runtime is not None and self._sandbox is not None:
            self.logger.warning("Deployment is already started; ignoring duplicate start()")
            return

        self.logger.info("Starting Modal sandbox")
        self._hooks.on_custom_step("Starting Modal sandbox")
        started = time.monotonic()
        token = self._get_token()
        encrypted, unencrypted, extra_kwargs = _tls_port_config(
            self._modal_kwargs,
            self._port
        )
        try:
            self._sandbox = await modal.Sandbox.create.aio(
                "usr/bin/env",
                "bash",
                "-c",
                self._start_swerex_cmd(token),
                image=self._image,
                timeout=int(self._deployment_timeout),
                encrypted_ports=encrypted,
                unencrypted_ports=unencrypted,
                app=self._app,
                **extra_kwargs,
            )
            tunnels = await self._sandbox.tunnels.aio()
            tunnel = tunnels[self._port]
            elapsed = time.monotonic() - started 
            log_url = await self.get_modal_log_url()
            self.logger.info("Sandbox %s created in %.2fs", self._sandbox.object_id, elapsed)
            self.logger.info("Model logs: %s", log_url)
            await asyncio.sleep(1)
            self.logger.info("Starting SWE-ReX runtime at %s", tunnel.url)
            self._hooks.on_custom_step("Starting runtime")
            self._runtime = RemoteRuntime(
                host=tunnel.url,
                timeout=self._runtime_timeout,
                auth_token=token,
                logger=self.logger,
            )
            remaining = max(0, self._startup_timeout - elapsed)
            await self._wait_until_alive(timeout=remaining)
        except Exception as exc:
            details = [f"{type(exc).__name__}: {exc}"]
            if self._sandbox is not None:
                details.append(f"sandbox_id={self._sandbox.object_id}")
                try:
                    details.append(f"logs={await self.get_modal_log_url()}")
                except Exception: pass
                try:
                    await self._sandbox.terminate.aio()
                except: pass
            self._runtime = None
            self._sandbox = None
            raise RuntimeError(
                "Modal sandbox started, but the SWE-ReX control runtime did not "
                "become reachable. " + " | ".join(details)
            ) from exc

class Environment:
    """ Exc bash cmd in a Modal sandbox via swe-rex"""

    def __init__(
        self,
        image: "str | PurePath | modal.Image" = "python:3.11",
        cwd: str = "/",
        startup_timeout: float = 600,
        runtime_timeout: float = 600,
        deployment_timeout: float = 600,
        install_pipx: bool = True,
        modal_sandbox_kwargs: dict[str, Any] | None = None,
    ):
        self.cwd = cwd
        self.env__defaults: dict[str, str] = {}
        self.deployment = AssignmentModelDeployment(
            image=image,
            startup_timeout=startup_timeout,
            runtime_timeout=runtime_timeout,
            deployment_timeout=deployment_timeout,
            install_pipx=install_pipx,
            modal_sandbox_kwargs=modal_sandbox_kwargs,
        )

        async def _start():
            await self.deployment.start()
            await self.deployment.is_alive()

        asyncio.run(_start())


        self.systam, self.release, self.version, self.machine = self.execute(
            "uname -s; uname -r; uname -v; uname -m"
        )["output"].splitlines()

    def is_alive(self) -> bool:
        sandbox = self.deployment._sandbox
        return sandbox is not None and sandbox.poll() is None

    def execute(
        self,
        command: str | list[str],
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool | None = True,
        check: bool = False,
    ) -> dict:
        shell = True if shell is None else shell
        arguments = {
            "command": command,
            "timeout": timeout,
            "env": {**self.env_defaults, **(env or {})} or None,
            "shell": shell,
            "check": check,
            "merge_output_streams": False,
        }
        if cwd is not None:
            arguments["cwd"] = cwd
        arguments.setdefault("cwd", self.cwd)

        try:
            result = asyncio.run(self.deployment.runtime.execute(Command(**arguments)))
            output = {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "output": result.output,
                "returncode": result.exit_code,
                "exception_info": "",
            }
            if result.stderr:
                output["output"] += result.stderr
        except Exception as e:
            if not self.is_alive():
                raise RuntimeError(
                    "The sandbox is no longer running, so no further commands can "
                    f"be executed. Last error: {e}"
                ) from e

            output = {
                "stdout": "",
                "stderr": str(e) if str(e) else "",
                "output": str(e) if str(e) else "",
                "returncode": -1,
                "exception_info": f"An error occurred while executing the command: {e}",
                "extra": {"exception_type": type(e).__name__, "exception": str(e)},
            }

        return output

    def stop(self, timeout: float=10):
        async def _stop():
            sandbox = self.deployment._sandbox
            try:
                await asyncio.wait_for(self.deployment.stop(), timeout=timeout)
            finally:
                if sandbox is not None:
                    await asyncio.wait_for(sandbox.terminate.aio(), timeout=timeout)


        asyncio.run(_stop())

    def tunnel_url(self, port: int) -> str:
        async def _tunnel_url() -> str:
            tunnels = await self.deployment.sandbox.tunnels.aio()
            try:
                return tunnels[port].url
            except KeyError as exc:
                forwarded = ", ".join(str(item) for item in sorted(tunnels)) or "none"
                raise ValueError(
                    f"Port {port} was not forwarded. Available forwarded ports: {forwarded}."
                ) from exc 

        return asyncio.run(_tunnel_url())

    def __enter__(self):
        """Enter a `with` block. The sandbox is already running by this point."""
        return self

    def __exit__(self, *exc):
        """Terminate the sandbox on leaving a `with` block, including on error."""
        self.stop()
