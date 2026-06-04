import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SCRIPT_DIR = Path(__file__).parent

FFMPEG_ZIP_URL = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-8.0.1-essentials_build.zip"
FFMPEG_EXES = {"ffmpeg.exe", "ffprobe.exe"}


def _install_ffmpeg_windows():
    import urllib.request
    import zipfile
    import io

    dest = SCRIPT_DIR / "ffmpeg"
    dest.mkdir(exist_ok=True)

    print("Downloading ffmpeg...", flush=True)
    with urllib.request.urlopen(FFMPEG_ZIP_URL) as r:
        total = int(r.headers.get("Content-Length", 0))
        buf = io.BytesIO()
        done = 0
        chunk = 65536
        while True:
            block = r.read(chunk)
            if not block:
                break
            buf.write(block)
            done += len(block)
            if total:
                pct = done * 100 // total
                print(f"\r  {pct}%  {done // (1024*1024)} MB / {total // (1024*1024)} MB", end="", flush=True)
    print("\nExtracting...", flush=True)

    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        for entry in zf.namelist():
            name = Path(entry).name
            if name in FFMPEG_EXES:
                data = zf.read(entry)
                (dest / name).write_bytes(data)
                print(f"  extracted {name}")

    print(f"ffmpeg ready in {dest}")


def _check_env() -> list[tuple[str, str]]:
    issues = []

    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    local_ffmpeg = SCRIPT_DIR / "ffmpeg" / exe
    if not local_ffmpeg.exists() and not shutil.which("ffmpeg"):
        if sys.platform == "win32":
            issues.append((
                "ffmpeg not found",
                f"ffmpeg is required for audio conversion.\n"
                f"  Run:  python nodex_dl.py setup-ffmpeg\n"
                f"  This will download and install it automatically."
            ))
        else:
            issues.append((
                "ffmpeg not found",
                f"Install ffmpeg:\n"
                f"  Ubuntu/Debian:  sudo apt install ffmpeg\n"
                f"  macOS:          brew install ffmpeg\n"
                f"  Or place ffmpeg binary in:  {SCRIPT_DIR / 'ffmpeg' / 'ffmpeg'}"
            ))

    missing_pkgs = []
    for mod, pkg in [("yt_dlp", "yt-dlp"), ("mutagen", "mutagen"), ("PIL", "Pillow"),
                     ("rich", "rich"), ("click", "click"), ("requests", "requests"), ("dotenv", "python-dotenv")]:
        try:
            __import__(mod)
        except ImportError:
            missing_pkgs.append(pkg)

    if missing_pkgs:
        issues.append((
            "Python packages missing",
            f"Run:  pip install {' '.join(missing_pkgs)}\n"
            f"  Or:  pip install -r \"{SCRIPT_DIR / 'requirements.txt'}\""
        ))

    return issues


_ENV_ISSUES = _check_env()

try:
    import click
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Prompt
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, DownloadColumn, TransferSpeedColumn
    from dotenv import load_dotenv
    RICH_OK = True
except ImportError:
    RICH_OK = False

if RICH_OK:
    load_dotenv(SCRIPT_DIR / ".env")
    console = Console()

BANNER = """\
[bold cyan]
 ███╗   ██╗ ██████╗ ██████╗ ███████╗██╗  ██╗   ██████╗ ██╗    ██╗
 ████╗  ██║██╔═══██╗██╔══██╗██╔════╝╚██╗██╔╝   ██╔══██╗██║    ██║
 ██╔██╗ ██║██║   ██║██║  ██║█████╗   ╚███╔╝    ██████╔╝██║ █╗ ██║
 ██║╚██╗██║██║   ██║██║  ██║██╔══╝   ██╔██╗    ██╔═══╝ ██║███╗██║
 ██║ ╚████║╚██████╔╝██████╔╝███████╗██╔╝ ██╗██╗██║     ╚███╔███╔╝
 ╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝╚═╝      ╚══╝╚══╝
[/bold cyan]
[bold yellow]              ♪  Song Downloader — nodex.pw  ♪[/bold yellow]
"""

FORMATS = {
    "1":  ("mp3",  "320",      "MP3  320 kbps"),
    "2":  ("mp3",  "256",      "MP3  256 kbps"),
    "3":  ("mp3",  "128",      "MP3  128 kbps"),
    "4":  ("flac", "lossless", "FLAC Lossless"),
    "5":  ("wav",  "lossless", "WAV  Lossless"),
    "6":  ("m4a",  "best",     "M4A / AAC Best"),
    "7":  ("alac", "lossless", "ALAC Lossless"),
    "8":  ("ogg",  "best",     "OGG  Vorbis"),
    "9":  ("opus", "best",     "OPUS"),
    "10": ("mp4",  "best",     "MP4  Video + Audio"),
}

PLATFORM_COLORS = {
    "youtube":     "[bold red]YouTube[/bold red]",
    "spotify":     "[bold green]Spotify[/bold green]",
    "apple_music": "[bold white]Apple Music[/bold white]",
}


def print_banner():
    console.print(BANNER)


def print_env_issues():
    if not _ENV_ISSUES:
        return
    for title, detail in _ENV_ISSUES:
        console.print(Panel(
            detail,
            title=f"[bold red]  {title}  [/bold red]",
            border_style="red",
            expand=False,
        ))
    console.print()


def print_format_menu():
    table = Table(border_style="cyan", show_header=True, header_style="bold cyan")
    table.add_column("#", style="bold yellow", width=4, justify="right")
    table.add_column("Format", style="bold white", min_width=22)
    table.add_column("Type", style="dim")

    for key, (fmt, quality, label) in FORMATS.items():
        t = "Lossless" if quality == "lossless" else ("Video" if fmt == "mp4" else f"{quality} kbps" if quality.isdigit() else "Best quality")
        table.add_row(key, label, t)

    console.print(table)


def pick_format() -> tuple[str, str]:
    print_format_menu()
    console.print()
    choice = Prompt.ask("[bold cyan]Choose format[/bold cyan]", choices=list(FORMATS.keys()), default="1")
    fmt, quality, label = FORMATS[choice]
    console.print(f"[dim]→[/dim] [green]{label}[/green]")
    return fmt, quality


def _make_progress_hook(progress: Progress, task_id):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            fname = Path(d.get("filename", "")).name[:50]
            if total > 0:
                progress.update(task_id, completed=done, total=total, description=f"[cyan]{fname}[/cyan]")
        elif d["status"] == "finished":
            progress.update(task_id, description="[green]Processing...[/green]")
    return hook


def run_download(url: str, fmt: str, quality: str, output_dir: str):
    if _ENV_ISSUES:
        print_env_issues()
        console.print("[yellow]Fix the issues above before downloading.[/yellow]")
        return

    from platforms import download_track, detect_platform

    platform = detect_platform(url)
    console.print(f"  Platform : {PLATFORM_COLORS.get(platform, platform)}")
    console.print(f"  Format   : [bold]{fmt.upper()}[/bold]  Quality: [bold]{quality}[/bold]")
    console.print(f"  Output   : [dim]{output_dir}[/dim]")
    console.print()

    downloaded = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Waiting...", total=None)
        hook = _make_progress_hook(progress, task_id)

        try:
            result = download_track(url, fmt, quality, output_dir, progress_callback=hook)
            downloaded.extend(result)
            progress.update(task_id, completed=progress.tasks[task_id].total or 100,
                            description="[bold green]Done[/bold green]")
        except (ValueError, RuntimeError) as e:
            progress.stop()
            console.print(f"\n[bold red]Error:[/bold red] {e}")
            return
        except Exception as e:
            progress.stop()
            console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")
            return

    console.print()
    if downloaded:
        lines = "\n".join(f"[green]✓[/green]  {Path(f).name}" for f in downloaded)
        console.print(Panel(lines, title="[bold green]Downloaded[/bold green]", border_style="green", expand=False))
    else:
        console.print("[yellow]Nothing was downloaded.[/yellow]")


def interactive_loop():
    print_env_issues()

    while True:
        console.print("[bold]Paste URL[/bold] [dim](YouTube / Spotify / Apple Music)[/dim]  or  [bold red]q[/bold red] to quit")
        url = Prompt.ask("[bold cyan]URL[/bold cyan]")

        if url.strip().lower() in ("q", "quit", "exit", ""):
            console.print("\n[bold cyan]Bye![/bold cyan]")
            break

        output_dir = Prompt.ask(
            "[bold]Output directory[/bold]",
            default=str(Path.home() / "Music"),
        )

        console.print()
        fmt, quality = pick_format()
        console.print()

        run_download(url.strip(), fmt, quality, output_dir)
        console.print()

        again = Prompt.ask("[bold]Download another?[/bold]", choices=["y", "n"], default="y")
        if again == "n":
            console.print("\n[bold cyan]Bye![/bold cyan]")
            break
        console.print()


# --- fallback for missing rich/click ---

def _no_rich_main():
    for title, detail in _ENV_ISSUES:
        print(f"\n[!] {title}")
        print(f"    {detail}\n")
    sys.exit(1)


if not RICH_OK:
    _no_rich_main()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        print_banner()
        interactive_loop()


@cli.command("download")
@click.argument("url")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["mp3", "flac", "wav", "m4a", "alac", "ogg", "opus", "mp4"]),
              default=None, help="Output format")
@click.option("--quality", "-q",
              type=click.Choice(["320", "256", "192", "128", "best"]),
              default="320", show_default=True, help="Bitrate for lossy formats")
@click.option("--output", "-o",
              default=str(Path.home() / "Music"), show_default=True, help="Destination directory")
def cmd_download(url: str, fmt: str | None, quality: str, output: str):
    """Download a track, album or playlist from URL."""
    print_banner()
    if fmt is None:
        console.print()
        fmt, quality = pick_format()
    console.print()
    run_download(url, fmt, quality, output)


@cli.command("setup-ffmpeg")
def cmd_setup_ffmpeg():
    """Download and install ffmpeg into the ffmpeg\\ folder (Windows)."""
    if sys.platform != "win32":
        console.print("[yellow]Use your package manager: apt install ffmpeg / brew install ffmpeg[/yellow]")
        return
    exe = SCRIPT_DIR / "ffmpeg" / "ffmpeg.exe"
    if exe.exists():
        console.print("[green]ffmpeg already installed.[/green]")
        return
    try:
        _install_ffmpeg_windows()
        console.print("\n[bold green]ffmpeg installed successfully.[/bold green]")
        console.print("Restart nodex_dl.py — everything should work now.")
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")


@cli.command("search")
@click.argument("query")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["mp3", "flac", "wav", "m4a", "alac", "ogg", "opus", "mp4"]),
              default=None)
@click.option("--quality", "-q",
              type=click.Choice(["320", "256", "192", "128", "best"]),
              default="320")
@click.option("--output", "-o", default=str(Path.home() / "Music"))
def cmd_search(query: str, fmt: str | None, quality: str, output: str):
    """Search YouTube and download the first result."""
    print_banner()
    if fmt is None:
        console.print()
        fmt, quality = pick_format()
    console.print()
    run_download(f"ytsearch1:{query}", fmt, quality, output)


if __name__ == "__main__":
    cli()
