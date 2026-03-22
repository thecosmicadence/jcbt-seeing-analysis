import paramiko
import os
from scp import SCPClient

def file_transfer(remote_host,remote_port,username,password,remote_path,local_path):
    try:
        # Initialize ssh client:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # connect to remote server
        print(f"connecting to {remote_host}")
        ssh.connect(remote_host, port = remote_port, username=username, password=password)

        # open a sftp session
        sftp = ssh.open_sftp()
        if not os.path.exists(local_path):
            os.makedirs(local_path)

        print(f" Fetching files from {remote_path}.....\n")
        files = sftp.listdir(remote_path)
        for filename in files:
            remote_file = os.path.join(remote_path,filename)
            local_file = os.path.join(local_path,filename)
            choice = input(f"Transfer {filename}? (y/n):").lower()
            if choice == "y":
                print(f"Downloading {filename}")
                sftp.get(remote_file, local_file)
            else:
                print(f"f Skipping {filename}")

        #close connection
        sftp.close()
        ssh.close()
        print("File Transfer Complete")

    except Exception as e:
        print(f"An error occured:{e}")
# configure
#Remote server details
HOST= '192.168.100.xxx'
PORT=22
USERNAME= 'USERNAME'
PASSWORD= 'PASS'
Local_dir= "/home/hp/Desktop/file_transfer_test"
Remote_path="/home/luciferat022/11mar_2026"
Local_path= os.path.join(Local_dir,os.path.basename(Remote_path))
file_transfer(HOST,PORT,USERNAME,PASSWORD,Remote_path,Local_path)





