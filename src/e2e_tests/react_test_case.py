import subprocess
import time
import os
import signal
import atexit
from adacs_django_playwright.adacs_django_playwright import PlaywrightTestCase

# Module-level variables to store the Vite server process
vite_process = None
react_app_built = False

FRONTEND_PORT = 4173
BACKEND_PORT = 8000


def build_react_app():
    """Build the React app using npm run build."""
    global react_app_built
    
    if react_app_built:
        return

    print("Building React app...")
    # Path to the react directory
    react_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "react"
    )

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=react_dir,
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            VITE_FRONTEND_URL=f"http://localhost:{FRONTEND_PORT}",
            VITE_BACKEND_URL=f"http://localhost:{BACKEND_PORT}",
        ),
    )

    if result.returncode != 0:
        print(f"Error building React app: {result.stderr}")
        raise Exception(f"Failed to build React app: {result.stderr}")

    react_app_built = True
    print("React app built successfully")


def start_vite_preview():
    """Start the Vite preview server to serve the built React app."""
    global vite_process

    if vite_process is not None:
        return

    print("Starting Vite preview server...")
    # Path to the react directory
    react_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "react"
    )

    # Start vite preview server
    vite_process = subprocess.Popen(
        [
            "npm",
            "run",
            "preview",
            "--",
            "--port",
            "4173",
            "--strictPort",
        ],
        cwd=react_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,  # Use process group for easier termination
    )

    # Wait for server to start (could be improved with actual readiness check)
    max_wait = 10  # seconds
    start_time = time.time()

    while time.time() - start_time < max_wait:
        # Check if process is still running
        if vite_process.poll() is not None:
            stderr = vite_process.stderr.read().decode("utf-8")
            raise Exception(f"Vite preview server failed to start: {stderr}")

        # Try to connect to the server
        try:
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 4173))
            sock.close()

            if result == 0:
                print("Vite preview server started successfully")
                return
        except Exception as e:
            print(f"Error checking server: {e}")

        time.sleep(0.5)

    # If we get here, the server didn't start in time
    stop_vite_preview()
    raise Exception("Timed out waiting for Vite preview server to start")


def stop_vite_preview():
    """Stop the Vite preview server."""
    global vite_process

    if vite_process is not None:
        print("Stopping Vite preview server...")
        try:
            # Kill the process group
            os.killpg(os.getpgid(vite_process.pid), signal.SIGTERM)
            vite_process.wait(timeout=5)
        except Exception as e:
            print(f"Error stopping Vite preview server: {e}")
            # Try to force kill if normal termination fails
            try:
                os.killpg(os.getpgid(vite_process.pid), signal.SIGKILL)
            except:
                pass

        vite_process = None
        print("Vite preview server stopped")


# Register the stop_vite_preview function to be called when the Python interpreter exits
atexit.register(stop_vite_preview)


class ReactPlaywrightTestCase(PlaywrightTestCase):
    """
    A test case class that extends PlaywrightTestCase to add support for testing
    the React frontend served by Vite preview.
    """

    port = BACKEND_PORT

    @classmethod
    def setUpClass(cls):
        """Set up the test environment."""
        super().setUpClass()
        # Ensure React app is built and Vite server is running
        build_react_app()
        start_vite_preview()

    @property
    def react_url(self):
        """Return the URL of the Vite preview server."""
        return f"http://localhost:{FRONTEND_PORT}"
