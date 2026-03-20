"""
Health check server for Render deployment
Binds to $PORT to satisfy Render's health check.
"""
import http.server
import socketserver
import threading
from loguru import logger
from config import get_settings

settings = get_settings()

def run_health_check():
    """Starts a tiny HTTP server on $PORT in a separate thread."""
    class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        
        def log_message(self, format, *args):
            return # Silent health checks

    port = settings.port
    
    # Render provides PORT as an env var, pydantic-settings handles it
    try:
        httpd = socketserver.TCPServer(("", port), HealthCheckHandler)
        logger.info(f"📡 Health check server listening on port {port}")
        
        # Start the server in a daemon thread
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
    except Exception as e:
        logger.error(f"Failed to start health check server: {e}")
