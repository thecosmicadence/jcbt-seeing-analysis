import sys
import getpass
import socket
import stat
from smb.SMBConnection import SMBConnection
import paramiko

# Global dictionary to store credentials for silent reconnects during the loop
SERVER_CREDS = {}

class MockFileAttribute:
    def __init__(self, filename, isDirectory):
        self.filename = filename
        self.isDirectory = isDirectory

class MockShare:
    def __init__(self, name):
        self.name = name

class SSHConnectionWrapper:
    def __init__(self, ip, username, password):
        self.ip = ip
        self.username = username
        self.password = password
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.sftp = None
        self.connected = False

    def connect(self):
        try:
            # We use timeout=5 for quick fail
            self.ssh.connect(self.ip, port=22, username=self.username, password=self.password, timeout=5)
            self.sftp = self.ssh.open_sftp()
            self.connected = True
            return True
        except Exception as e:
            # Silent during normal loop reconnects
            return False

    def listShares(self):
        # Return a root share representation for the user to select
        return [MockShare('/')]

    def listPath(self, share_name, path):
        if not path or path == '/':
            full_path = '/'
        else:
            full_path = path

        files = []
        try:
            for attr in self.sftp.listdir_attr(full_path):
                is_dir = stat.S_ISDIR(attr.st_mode)
                files.append(MockFileAttribute(attr.filename, is_dir))
        except IOError as e:
            print(f"Error reading path {full_path}: {e}")
            raise e
        return files

    def retrieveFile(self, share_name, remote_filepath, fp):
        # Ensure path does not have double slashes from appending
        clean_path = remote_filepath.replace('//', '/')
        self.sftp.getfo(clean_path, fp)

    def close(self):
        if self.sftp:
            try:
                self.sftp.close()
            except:
                pass
        if self.ssh:
            try:
                self.ssh.close()
            except:
                pass
        self.connected = False

def check_port(ip, port):
    """Helper function to cleanly check if a specific port is open."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        result = sock.connect_ex((ip, port))
        return result == 0
    except:
        return False
    finally:
        sock.close()

def detect_os(ip):
    """Check ports 445 and 22 to accurately detect Windows vs Linux."""
    # Windows 11 often has SSH (22) open, so we MUST check SMB (445) first.
    if check_port(ip, 445):
        return 'windows'
    elif check_port(ip, 22):
        return 'linux'
    else:
        # Fallback to windows if neither responds within the timeout
        return 'windows'

def setup_smb_connection():
    """Interactively get credentials and establish the first connection."""
    print("--- Server Connection Setup ---")
    SERVER_CREDS['client'] = socket.gethostname() # Automatically gets your Fedora hostname
    SERVER_CREDS['ip'] = input("Enter Server IP (e.g., 192.168.1.100): ").strip()

    print("Checking system type...")
    os_type = detect_os(SERVER_CREDS['ip'])
    SERVER_CREDS['protocol'] = 'ssh' if os_type == 'linux' else 'smb'
    print(f"Detected system as: {'Linux (SSH)' if os_type == 'linux' else 'Windows (SMB)'}")

    if SERVER_CREDS['protocol'] == 'smb':
        SERVER_CREDS['server'] = input("Enter Windows Server Name (NetBIOS name): ").strip()
        SERVER_CREDS['user'] = input("Enter Windows Username: ").strip()
        SERVER_CREDS['pass'] = getpass.getpass("Enter Windows Password: ")
    else:
        SERVER_CREDS['server'] = ''
        SERVER_CREDS['user'] = input("Enter Linux Username: ").strip()
        SERVER_CREDS['pass'] = getpass.getpass("Enter Linux Password: ")

    conn = get_smb_connection(verbose=True)
    if not conn:
        print("\nFailed to connect. Please check your IP, Server Name, and credentials.")
        sys.exit(1)
    
    print("Connection successful!\n")
    return conn

def get_smb_connection(verbose=False):
    """Attempt a connection based on the registered protocol."""
    
    if SERVER_CREDS.get('protocol') == 'ssh':
        conn = SSHConnectionWrapper(SERVER_CREDS['ip'], SERVER_CREDS['user'], SERVER_CREDS['pass'])
        if conn.connect():
            if verbose:
                print("Connected via SSH (Port 22).")
            return conn
        return None

    # SMB Connection
    # Attempt 1: Modern Direct TCP (Port 445)
    try:
        conn = SMBConnection(
            SERVER_CREDS['user'], 
            SERVER_CREDS['pass'], 
            SERVER_CREDS['client'], 
            SERVER_CREDS['server'], 
            use_ntlm_v2=True,
            is_direct_tcp=True
        )
        if conn.connect(SERVER_CREDS['ip'], 445):
            if verbose:
                print("Connected via Direct TCP (Port 445).")
            return conn
    except Exception as e:
        if verbose:
            print(f"Port 445 failed: {e}. Trying legacy port...")

    # Attempt 2: Legacy NetBIOS (Port 139)
    try:
        conn_legacy = SMBConnection(
            SERVER_CREDS['user'], 
            SERVER_CREDS['pass'], 
            SERVER_CREDS['client'], 
            SERVER_CREDS['server'], 
            use_ntlm_v2=True,
            is_direct_tcp=False # Explicitly turn off Direct TCP
        )
        if conn_legacy.connect(SERVER_CREDS['ip'], 139):
            if verbose:
                print("Connected via Legacy NetBIOS (Port 139).")
            return conn_legacy
    except Exception as e:
        if verbose:
            print(f"Port 139 failed: {e}.")

    return None

def select_smb_share(conn):
    """Ask the server for available shares and let the user pick one."""
    if SERVER_CREDS.get('protocol') == 'ssh':
        # Skip share selection for SSH
        return '/'

    shares = conn.listShares()
    # Filter out hidden administrative shares (which usually end with '$')
    available_shares = [s.name for s in shares if not s.name.endswith('$')]
    
    if not available_shares:
        print("No readable shares found on this server.")
        sys.exit(1)

    print("--- Available Network Shares ---")
    for i, share in enumerate(available_shares):
        print(f"[{i + 1}] {share}")
        
    while True:
        try:
            choice = int(input("\nEnter the number of the share you want to access: "))
            if 1 <= choice <= len(available_shares):
                selected_share = available_shares[choice - 1]
                print(f"Selected Share: {selected_share}\n")
                return selected_share
            print("Invalid choice.")
        except ValueError:
            print("Please enter a valid number.")

def select_remote_folder(conn, share_name):
    """Navigate the chosen share interactively to drill down to the specific folder."""
    current_path = "/"
    while True:
        try:
            file_attributes = conn.listPath(share_name, current_path)
        except Exception as e:
            print(f"Error reading path {current_path}: {e}")
            if current_path != "/":
                import posixpath
                current_path = posixpath.dirname(current_path)
                continue
            else:
                sys.exit(1)

        folders = [
            item.filename for item in file_attributes 
            if item.isDirectory and item.filename not in ['.', '..']
        ]
        folders.sort()

        # Display UI
        print(f"\n--- Browsing: {share_name if share_name != '/' else ''}{current_path} ---")
        print("[0] *** SELECT AND MONITOR THIS FOLDER ***")
        if current_path != "/":
            print("[u] Go UP one directory (..)")

        for index, folder in enumerate(folders):
            print(f"[{index + 1}] {folder}")

        choice = input("\nEnter choice ('0' to select, 'u' to go up, or number to enter folder): ").strip().lower()

        if choice == '0':
            print(f"Monitoring remote folder: {current_path}\n")
            return current_path
        elif choice == 'u' and current_path != "/":
            import posixpath
            current_path = posixpath.dirname(current_path.rstrip('/'))
            if not current_path:
                current_path = "/"
        else:
            try:
                choice_int = int(choice)
                if 1 <= choice_int <= len(folders):
                    selected = folders[choice_int - 1]
                    if current_path == "/":
                        current_path = f"/{selected}"
                    else:
                        current_path = f"{current_path}/{selected}"
                else:
                    print("Invalid folder number.")
            except ValueError:
                print("Invalid input.")
