import subprocess
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Generator, Optional

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from metta.common.util.text_styles import bold, cyan, green, red, yellow
from metta.setup.utils import error, info, prompt_choice

SCP_TARGETS = [
    ("~/.claude/settings.json", True, "Claude settings"),
    ("~/.claude/CLAUDE.md", True, "Claude global instructions"),
    ("~/.claude/skills", False, "Claude skills"),
    ("~/.claude/plugins", False, "Claude plugins"),
    ("~/.codex/instructions.md", False, "Codex instructions"),
    ("~/.config/gh", True, "GitHub CLI config"),
]

DEFAULT_INSTANCE_TYPE = "m6i.2xlarge"

app = typer.Typer(
    help="Manage remote EC2 coding sandboxes.",
    rich_markup_mode="rich",
)

_AUTH_HINTS = {
    "credentials": "AWS auth failed. Run: aws sso login --profile sandbox",
    "expired": "AWS session expired. Run: aws sso login --profile sandbox",
    "sso token": "AWS SSO token expired. Run: aws sso login --profile sandbox",
    "unable to locate": "AWS credentials not found. Run: aws sso login --profile sandbox",
}


@contextmanager
def _friendly_auth_errors() -> Generator[None, None, None]:
    try:
        yield
    except typer.Exit:
        raise
    except Exception as exc:
        msg = str(exc).lower()
        for pattern, hint in _AUTH_HINTS.items():
            if pattern in msg:
                error(hint)
                raise typer.Exit(1) from None
        raise


def _ssh_opts(key_path: Path, connect_timeout: int | None = None) -> list[str]:
    opts = [
        "-i",
        str(key_path),
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
    ]
    if connect_timeout is not None:
        opts.extend(["-o", f"ConnectTimeout={connect_timeout}"])
    return opts


_COMMANDS = {
    "new": lambda: cmd_new(),
    "list": lambda: cmd_list(),
    "ssh": lambda: cmd_ssh(),
    "down": lambda: cmd_down(),
    "bake": lambda: cmd_bake(),
}


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context) -> None:
    if ctx.resilient_parsing:
        return
    if ctx.invoked_subcommand is not None:
        return
    action = prompt_choice(
        "What would you like to do?",
        [
            ("new", "Launch a new box"),
            ("list", "List my boxes"),
            ("ssh", "Connect to a box"),
            ("down", "Tear down a box"),
            ("bake", "Bake a pre-built AMI"),
        ],
    )
    _COMMANDS[action]()


@app.command(name="list", help="List my boxes.")
def cmd_list() -> None:
    with _friendly_auth_errors():
        from metta.setup.tools.sandbox.ec2 import (  # noqa: PLC0415
            get_ec2_client,
            get_username,
            list_user_instances,
        )

        ec2 = get_ec2_client()
        username = get_username()
        instances = list_user_instances(ec2, username)

    if not instances:
        info("No boxes found.")
        print(f"  Launch one with: {green('metta box new')}")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("State")
    table.add_column("IP")
    table.add_column("Type")

    state_colors = {"running": "green", "pending": "yellow", "stopping": "yellow"}
    for inst in instances:
        color = state_colors.get(inst.state, "red")
        table.add_row(
            inst.name,
            f"[{color}]{inst.state}[/{color}]",
            inst.ip or "-",
            inst.instance_type,
        )

    Console().print(table)


@app.command(name="ssh", help="SSH into a running box.")
def cmd_ssh(
    name: Annotated[Optional[str], typer.Argument(help="Box name to connect to")] = None,
) -> None:
    with _friendly_auth_errors():
        from metta.setup.tools.sandbox.ec2 import (  # noqa: PLC0415
            ensure_key_pair,
            get_ec2_client,
            get_instance_by_name,
            get_username,
            list_user_instances,
        )

        ec2 = get_ec2_client()
        username = get_username()
        _, private_key_path = ensure_key_pair(ec2, username)

        if name:
            inst = get_instance_by_name(ec2, name, username=username)
            if not inst:
                error(f"Box '{name}' not found.")
                raise typer.Exit(1)
        else:
            instances = list_user_instances(ec2, username)
            running = [i for i in instances if i.state == "running"]
            if not running:
                error("No running boxes found.")
                raise typer.Exit(1)
            if len(running) == 1:
                inst = running[0]
            else:
                chosen = prompt_choice(
                    "Which box?",
                    [(i.name, f"{i.name} ({i.ip})") for i in running],
                )
                inst = next(i for i in running if i.name == chosen)

    if inst.state != "running":
        error(f"Box '{inst.name}' is {inst.state}, not running.")
        raise typer.Exit(1)

    if not inst.ip:
        error(f"Box '{inst.name}' has no public IP.")
        raise typer.Exit(1)

    result = subprocess.run(
        [
            "ssh",
            "-i",
            str(private_key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"ubuntu@{inst.ip}",
        ]
    )
    if result.returncode != 0:
        error(f"SSH connection failed with exit code {result.returncode}")
        raise typer.Exit(1)


@app.command(name="down", help="Terminate a box.")
def cmd_down(
    name: Annotated[Optional[str], typer.Argument(help="Box name to tear down")] = None,
) -> None:
    with _friendly_auth_errors():
        from metta.setup.tools.sandbox.ec2 import (  # noqa: PLC0415
            get_ec2_client,
            get_instance_by_name,
            get_username,
            list_user_instances,
            terminate_instance,
        )

        ec2 = get_ec2_client()
        username = get_username()

        if not name:
            instances = list_user_instances(ec2, username)
            if not instances:
                error("No boxes found.")
                raise typer.Exit(1)
            if len(instances) == 1:
                name = instances[0].name
            else:
                name = prompt_choice(
                    "Which box to tear down?",
                    [(i.name, f"{i.name} ({i.state})") for i in instances],
                )

        inst = get_instance_by_name(ec2, name, username=username)
        if not inst:
            error(f"Box '{name}' not found.")
            raise typer.Exit(1)

        print(f"Terminating {bold(name)}...")
        terminate_instance(ec2, inst.instance_id)
        print(f"{green('Done.')} {name} has been terminated.")


@app.command(name="bake", help="Bake a pre-built AMI with dev tools for faster launches.")
def cmd_bake(
    instance_type: Annotated[str, typer.Option("--instance-type", help="EC2 instance type")] = DEFAULT_INSTANCE_TYPE,
) -> None:
    from datetime import datetime, timezone  # noqa: PLC0415

    import gitta as git_lib  # noqa: PLC0415

    github_token = git_lib.get_github_token()
    if not github_token:
        error("No GitHub token found. Run 'gh auth login' or set GITHUB_TOKEN.")
        raise typer.Exit(1)

    with _friendly_auth_errors():
        from metta.setup.tools.sandbox.ec2 import (  # noqa: PLC0415
            build_bake_user_data,
            create_baked_ami,
            ensure_key_pair,
            get_ec2_client,
            get_security_group,
            get_username,
            launch_instance,
            resolve_ubuntu_ami,
            terminate_instance,
            wait_for_image,
            wait_for_running,
        )

        ec2 = get_ec2_client()
        username = get_username()
        key_name, private_key_path = ensure_key_pair(ec2, username)
        sg_id = get_security_group(ec2)

        print("Resolving Ubuntu AMI...")
        base_ami = resolve_ubuntu_ami(ec2)

    user_data = build_bake_user_data(github_token)
    instance_name = f"{username}-bake-tmp"

    print("\nLaunching temp instance for baking...")
    print(f"  Instance type: {bold(instance_type)}")
    print(f"  Base AMI: {base_ami}")

    instance_id = launch_instance(
        ec2,
        name=instance_name,
        instance_type=instance_type,
        key_name=key_name,
        sg_id=sg_id,
        user_data=user_data,
        username=username,
        git_ref="bake",
        image_id=base_ami,
        repo="bake",
        volume_size=50,
    )

    print(f"  Instance ID: {instance_id}")
    print("Waiting for instance to start...")
    ip = wait_for_running(ec2, instance_id)
    print(f"  Public IP: {cyan(ip)}")

    print("Waiting for tools to install (this takes several minutes)...")
    ready = _poll_for_ready(ip, private_key_path, timeout=900)
    if not ready:
        print(yellow("Bake did not complete within timeout."))
        print(f"  Instance {instance_id} is still running — terminate manually if needed.")
        raise typer.Exit(1)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    ami_name = f"aicode-baked-{timestamp}"

    print(f"\nCreating AMI {bold(ami_name)}...")
    ami_id = create_baked_ami(ec2, instance_id, ami_name, username)
    print(f"  AMI ID: {ami_id}")

    print("Waiting for AMI to become available (this takes several minutes)...")
    wait_for_image(ec2, ami_id)

    print(f"Terminating temp instance {instance_id}...")
    terminate_instance(ec2, instance_id)

    print(f"\n{green('Baked AMI is ready!')}")
    print(f"  AMI: {cyan(ami_id)}")
    print(f"  Name: {ami_name}")
    print(f"  Use it: {green('metta box new')} (auto-detected)")


@app.command(name="new", help="Launch a new box.")
def cmd_new(
    name: Annotated[Optional[str], typer.Option("--name", help="Instance name")] = None,
    git_ref: Annotated[Optional[str], typer.Option("--git-ref", help="Git branch or commit")] = None,
    repo: Annotated[Optional[str], typer.Option("--repo", help="GitHub repo (org/name)")] = None,
    image_id: Annotated[Optional[str], typer.Option("--image-id", help="Override AMI ID")] = None,
    instance_type: Annotated[str, typer.Option("--instance-type", help="EC2 instance type")] = DEFAULT_INSTANCE_TYPE,
) -> None:
    import gitta as git_lib  # noqa: PLC0415

    github_token = git_lib.get_github_token()
    if not github_token:
        error("No GitHub token found. Run 'gh auth login' or set GITHUB_TOKEN.")
        raise typer.Exit(1)

    if not repo:
        remote_url = git_lib.get_remote_url()
        if remote_url and "github.com" in remote_url:
            repo = remote_url.split("github.com")[-1].strip("/:")
            if repo.endswith(".git"):
                repo = repo[:-4]
        else:
            repo = "Metta-AI/metta"

    if not git_ref:
        git_ref = git_lib.get_current_branch() or "main"

    with _friendly_auth_errors():
        from metta.setup.tools.sandbox.ec2 import (  # noqa: PLC0415
            build_launch_user_data,
            build_user_data,
            ensure_key_pair,
            get_ec2_client,
            get_next_instance_name,
            get_security_group,
            get_username,
            launch_instance,
            resolve_baked_ami,
            resolve_ubuntu_ami,
            wait_for_running,
        )

        ec2 = get_ec2_client()
        username = get_username()

        instance_name = name or get_next_instance_name(ec2, username)
        key_name, private_key_path = ensure_key_pair(ec2, username)
        sg_id = get_security_group(ec2)

        if image_id:
            ami_id = image_id
            ami_type = "custom"
        else:
            baked_ami = resolve_baked_ami(ec2)
            if baked_ami:
                ami_id = baked_ami
                ami_type = "baked"
            else:
                print("No baked AMI found, resolving Ubuntu AMI...")
                ami_id = resolve_ubuntu_ami(ec2)
                ami_type = "vanilla"

    if ami_type == "baked":
        user_data = build_launch_user_data(github_token, git_ref, repo)
    else:
        user_data = build_user_data(github_token, git_ref, repo)

    print(f"\nLaunching {bold(instance_name)}")
    print(f"  Repo: {cyan(repo)}")
    print(f"  Git ref: {cyan(git_ref)}")
    print(f"  Instance type: {bold(instance_type)}")
    print(f"  AMI: {ami_id} ({ami_type})")

    instance_id = launch_instance(
        ec2,
        name=instance_name,
        instance_type=instance_type,
        key_name=key_name,
        sg_id=sg_id,
        user_data=user_data,
        username=username,
        git_ref=git_ref,
        image_id=ami_id,
        repo=repo,
    )

    print(f"  Instance ID: {instance_id}")
    print("Waiting for instance to start...")
    ip = wait_for_running(ec2, instance_id)
    print(f"  Public IP: {cyan(ip)}")

    print("Waiting for sandbox setup to complete (this takes a few minutes)...")
    ready = _poll_for_ready(ip, private_key_path, timeout=600)
    if not ready:
        print(yellow("Setup did not complete within timeout. The box may still be initializing."))
        print(f"  Try: {green(f'metta box ssh {instance_name}')}")
        return

    _scp_credentials(ip, private_key_path)

    print(f"\n{green('Box is ready!')}")
    print(f"  {green(f'metta box ssh {instance_name}')}")


def _poll_for_ready(ip: str, key_path: Path, timeout: int = 600, interval: int = 5, tail: int = 30) -> bool:
    from metta.setup.tools.sandbox.ec2 import check_ssh_connection  # noqa: PLC0415

    ssh_cmd = ["ssh", *_ssh_opts(key_path, connect_timeout=interval), f"ubuntu@{ip}"]
    lines_seen = 0
    recent: deque[str] = deque(maxlen=tail)

    def _build_display() -> Group:
        body = Text("\n".join(recent), style="dim")
        panel = Panel(body, border_style="dim", height=min(len(recent) + 2, tail + 2))
        spinner = Spinner("dots", text="Setting up box...", style="cyan")
        return Group(panel, spinner)

    with Live(_build_display(), console=Console(), refresh_per_second=8, transient=True) as live:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if check_ssh_connection(ip, key_path):
                return True
            result = subprocess.run(
                [*ssh_cmd, "cat", "/var/log/cloud-init-output.log"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                lines = result.stdout.splitlines()
                for line in lines[lines_seen:]:
                    recent.append(line)
                lines_seen = len(lines)
                live.update(_build_display())
            time.sleep(interval)
    return False


def _scp_credentials(ip: str, key_path: Path) -> None:
    print(f"\nTransferring credentials to {bold(ip)}...")
    opts = _ssh_opts(key_path)

    for raw_path, required, label in SCP_TARGETS:
        local_path = Path(raw_path).expanduser()
        if not local_path.exists():
            if required:
                print(f"  {yellow('Missing')}  {label} ({raw_path})")
            else:
                print(f"  {yellow('Missing')}  {label} ({raw_path}) - optional")
            continue

        remote_path = raw_path.replace("~", "", 1)
        remote_parent = str(Path(remote_path).parent)
        if remote_parent != "/":
            subprocess.run(
                ["ssh", *opts, f"ubuntu@{ip}", "mkdir", "-p", f"~{remote_parent}"],
                capture_output=True,
            )

        result = subprocess.run(
            ["scp", "-rq", *opts, str(local_path), f"ubuntu@{ip}:~{remote_path}"],
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"  {green('Transferred')}  {label}")
        else:
            print(f"  {red('Failed')}  {label} ({raw_path})")
