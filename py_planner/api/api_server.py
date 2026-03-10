import http.server
import socketserver
import json
import threading
import socket

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass

class APIHandler(http.server.BaseHTTPRequestHandler):
    data_provider = None

    def do_GET(self):
        if self.path == '/api/data':
            try:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                if APIHandler.data_provider:
                    # Capture current data to avoid 'dict changed size' errors
                    import copy
                    try:
                        data = APIHandler.data_provider()
                        # Simple copy of top-level machines to be safer
                        data_copy = dict(data) 
                        json_str = json.dumps(data_copy)
                        self.wfile.write(json_str.encode('utf-8'))
                    except Exception as e:
                        error_msg = json.dumps({"error": str(e)})
                        self.wfile.write(error_msg.encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"error": "No data provider"}).encode('utf-8'))
            except Exception as e:
                print(f"API HANDLER ERROR: {e}")
        
        elif self.path == '/api/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "version": "3.6.6"}).encode('utf-8'))
        
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def start_api_server(data_provider, port=8000):
    APIHandler.data_provider = data_provider
    
    def run_server():
        try:
            # Reallow address reuse to prevent 'Address already in use' during rapid restarts
            socketserver.TCPServer.allow_reuse_address = True
            with ThreadedTCPServer(("", port), APIHandler) as httpd:
                print(f"API SERVER: Hosting on port {port} (Threaded)")
                httpd.serve_forever()
        except Exception as e:
            print(f"API SERVER ERROR: {e}")

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"