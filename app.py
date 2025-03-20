from flask import Flask, request, jsonify, render_template
import paramiko
from paramiko import RSAKey
import os
import re

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index1.html')

# Function to create a VM on Proxmox using uploaded file
def create_vm(user,file_path, hostname, port, username, private_key_path):
    try:
        # SSH client setup
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = RSAKey.from_private_key_file(private_key_path)
        ssh_client.connect(hostname, port=port, username=username, pkey=private_key)

        # Command to create VM using uploaded file
        command = f'/bin/bash /root/vm.sh  {user} {file_path}'  # Ensure this is the correct script
        print(command)
        stdin, stdout, stderr = ssh_client.exec_command(command)

        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error_message = stderr.read().decode()
            ssh_client.close()
            return {'status': 'error', 'message': f"VM creation failed: {error_message}"}

        # Capture the output from the shell script
        output = stdout.read().decode()

        # Use regular expression to extract the success message
        success_message = None
        match = re.search(r"✅ VM \d+ \(vm-\d+\) created, configured, and started successfully on Node \d+", output)
        if match:
            success_message = match.group(0)  # This will get the matched message
        
        # If we found the success message, return it, otherwise return an error
        if success_message:
            ssh_client.close()
            return {'status': 'success', 'message': success_message}
        else:
            ssh_client.close()
            return {'status': 'error', 'message': 'VM creation failed. Success message not found.'}

    except Exception as e:
        return {'status': 'error', 'message': f"VM creation failed: {str(e)}"}


# Function to upload a file to Proxmox
def upload_file_to_proxmox(local_file, remote_path, hostname, port, username, private_key_path, node_name):
    try:
        # Create an SSH client instance
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load the private key for authentication
        private_key = RSAKey.from_private_key_file(private_key_path)

        # Connect to the Proxmox node
        ssh_client.connect(hostname, port=port, username=username, pkey=private_key)

        # Ensure the directory exists on the Proxmox node (create if necessary)
        command = f"mkdir -p /mnt/storage1/{node_name}"
        stdin, stdout, stderr = ssh_client.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()

        # Check for errors while creating the directory
        if exit_status != 0:
            raise Exception(f"Failed to create directory: {stderr.read().decode()}")

        # Open an SFTP session to upload the file
        sftp_client = ssh_client.open_sftp()

        # Upload the file to the specified location
        sftp_client.put(local_file, remote_path)

        # Cleanly close the SFTP and SSH client
        sftp_client.close()
        ssh_client.close()

        return {'status': 'success', 'message': f"File {local_file} uploaded to Proxmox node"}
    except Exception as e:
        return {'status': 'error', 'message': f"Connection failed: {str(e)}"}

@app.route('/upload_file', methods=['POST'])
def handle_upload():
    if request.method == 'POST':
        # Get the uploaded file and username from the request
        file = request.files.get('file')
        username = request.form.get('username')

        if not file:
            return jsonify({'status': 'error', 'message': 'No file uploaded.'})

        if not username:
            return jsonify({'status': 'error', 'message': 'No username provided.'})

        # Create a directory with the username on the local server
        user_dir = os.path.join('/tmp', username)
        os.makedirs(user_dir, exist_ok=True)

        # Save the file to the user's directory
        temp_file_path = os.path.join(user_dir, file.filename)
        file.save(temp_file_path)

        # Define your Proxmox node details for SSH connection
        hostname = '192.168.1.191'  # Proxmox node IP
        username_proxmox = 'root'  # Proxmox username
        private_key_path = '/home/innuser002/.ssh/id_rsa'  # Path to private SSH key
        remote_path = f"/mnt/storage1/{username}/{file.filename}"

        # Call the function to upload the file to Proxmox
        result = upload_file_to_proxmox(temp_file_path, remote_path, hostname, 22, username_proxmox, private_key_path, username)

        # Remove the temporary file after upload
        os.remove(temp_file_path)

        # If upload is successful, prepare VM creation response
        if result['status'] == 'success':
            return jsonify({
                'status': 'success',
                'message': result['message'],
                'file_name': file.filename,
                'username': username
            })

        return jsonify(result)

@app.route('/create_vm', methods=['POST'])
def handle_create_vm():
    if request.method == 'POST':
        file_name = request.form.get('file_name')
        username = request.form.get('username')

        if not file_name or not username:
            return jsonify({'status': 'error', 'message': 'Missing file or username'})

        # Define your Proxmox node details for SSH connection
        hostname = '192.168.1.252'
        username_proxmox = 'root'
        private_key_path = '/home/innuser002/.ssh/id_rsa'

        # Call the function to create VM
        result = create_vm(username,file_name, hostname, 22, username_proxmox, private_key_path)

        return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, port=50001)
