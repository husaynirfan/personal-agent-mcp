from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn, subprocess, os, json, logging, glob, datetime, psutil
from dotenv import load_dotenv
from pathlib import Path

# --------------------------------------------------------------------
#  basic config & safety
# --------------------------------------------------------------------
load_dotenv()
SECRET = os.getenv("MCP_SECRET", "")
WHITELIST_CMDS = {
    "list": ["ls", "dir"],
    "disk": ["df", "wmic logicaldisk get size,freespace,caption"],
    "date": ["date", "time"],
}
LOGFILE = Path(__file__).with_suffix(".log")
logging.basicConfig(
    filename=LOGFILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

mcp = FastMCP(name="LocalPCController")

def _check_secret(secret: str):
    if secret != SECRET or secret == "":
        raise PermissionError("Invalid or missing secret token.")

# --------------------------------------------------------------------
#  helper utilities
# --------------------------------------------------------------------
def _run_subprocess(cmd: list[str], timeout: int = 10) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout, text=True, shell=False)
        return out.strip()[:2_000]  # truncate huge output
    except subprocess.CalledProcessError as e:
        return f"Command exited with code {e.returncode}: {e.output}"
    except subprocess.TimeoutExpired:
        return "Command timed-out."

# --------------------------------------------------------------------
#  TOOL 1 – safe shell commands
# --------------------------------------------------------------------
@mcp.tool()
def run_command(name: str, secret: str) -> str:
    """
    Run a **whitelisted** command on the host machine.
    Args:
        name: logical command name (list | disk | date).
        secret: the MCP secret key.
    """
    _check_secret(secret)
    if name not in WHITELIST_CMDS:
        return f"Command '{name}' not allowed."
    cmd = WHITELIST_CMDS[name]
    out = _run_subprocess(cmd)
    logging.info("run_command: %s -> %s", name, cmd)
    return out

# --------------------------------------------------------------------
#  TOOL 2 – system stats
# --------------------------------------------------------------------
@mcp.tool()
def system_info() -> str:
    """
    Returns basic CPU/RAM/disk usage.
    """
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    boot = datetime.datetime.fromtimestamp(psutil.boot_time()).isoformat()
    info = (
        f"CPU: {cpu}%\n"
        f"RAM: {mem.percent}% used of {round(mem.total/1e9,1)} GB\n"
        f"Uptime since: {boot}"
    )
    logging.info("system_info called")
    return info

# --------------------------------------------------------------------
#  TOOL 3 – quick file search
# --------------------------------------------------------------------
@mcp.tool()
def find_files(pattern: str, limit: int = 20) -> str:
    """
    Glob-style search from the user's home folder.
    """
    home = Path.home()
    matches = glob.glob(str(home / "**" / pattern), recursive=True)[:limit]
    logging.info("find_files: %s -> %d hits", pattern, len(matches))
    if not matches:
        return "No matches."
    return "\n".join(matches)

# --------------------------------------------------------------------
#  TOOL 4 – open file (non-blocking)
# --------------------------------------------------------------------
@mcp.tool()
def open_file(path: str, secret: str) -> str:
    """
    Opens a file with the default OS handler (e.g., PDF, image).
    """
    _check_secret(secret)
    abs_path = Path(path).expanduser().resolve()
    if not abs_path.exists():
        return "File not found."
    try:
        if os.name == "nt":
            os.startfile(abs_path)           # type: ignore
        elif sys.platform == "darwin":
            subprocess.Popen(["open", abs_path])
        else:
            subprocess.Popen(["xdg-open", abs_path])
        logging.info("open_file: %s", abs_path)
        return f"Opening {abs_path}"
    except Exception as e:
        return f"Failed: {e}"

# --------------------------------------------------------------------
#  HTTP wrapper & CORS
# --------------------------------------------------------------------
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]
app = mcp.http_app(middleware=middleware, path="/mcp/", stateless_http=True)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logging.info("%s %s -> %d", request.method, request.url.path, response.status_code)
    return response

if __name__ == "__main__":
    print("📟  LocalPCController MCP running on :8005")
    uvicorn.run(app, host="0.0.0.0", port=8005)
