import os
import paramiko

def connect_ssh(hostname, username, password):
    """Establish an SSH connection to the server."""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, username=username, password=password)
        return client
    except Exception as e:
        print(f"Failed to connect to {hostname}: {e}")
        return None

def get_metrics(ssh_client):
    """Fetch CPU, RAM, Disk space usage, and running services."""
    commands = {
        'cpu': "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\([0-9.]*\)%* id.*/\\1/' | awk '{print 100 - $1}'",
        'ram': "free -m | awk 'NR==2{printf \"Memory Usage: %s/%sMB (%.2f%%)\", $3,$2,$3*100/$2 }'",
        'disk': "df -h | awk '$NF==\"/\"{printf \"%d/%dGB (%s)\", $3,$2,$5}'",
    }

    # Fetching metrics for CPU, RAM, and Disk
    metrics = {}
    for key, command in commands.items():
        stdin, stdout, stderr = ssh_client.exec_command(command)
        metrics[key] = stdout.read().decode().strip()

    # Checking the status of specific services
    service_commands = {
        'nginx': "systemctl is-active nginx.service",
        'apache': "systemctl is-active apache2.service",
        'php': "systemctl is-active php7.4-fpm.service",  # Adjust based on your PHP version
        'mysql': "systemctl is-active mysql.service",
        'elasticsearch': "systemctl is-active elasticsearch.service",
        'varnish': "systemctl is-active varnish.service",
        'redis': "systemctl is-active redis.service",
        'rabbitmq': "systemctl is-active rabbitmq-server.service",
    }

    for service, command in service_commands.items():
        try:
            stdin, stdout, stderr = ssh_client.exec_command(command)
            status = stdout.read().decode().strip()
            metrics[service] = "running" if status == "active" else "stopped" if status == "inactive" else "not installed"
        except Exception:
            metrics[service] = "not installed"

    return metrics

def control_service(ssh_client, service_name, action):
    """Start or stop a service."""
    command = f"sudo systemctl {action} {service_name}.service"
    stdin, stdout, stderr = ssh_client.exec_command(command)
    return stdout.read().decode(), stderr.read().decode()

def get_databases(ssh_client, mysql_username, mysql_password):
    """Fetch the list of MySQL databases."""
    command = f"MYSQL_PWD={mysql_password} mysql -u{mysql_username} -e 'SHOW DATABASES;'"
    stdin, stdout, stderr = ssh_client.exec_command(command)
    databases = stdout.read().decode().strip().split('\n')[1:]  # Skip the header
    return databases

def create_database(ssh_client, mysql_username, mysql_password, db_name):
    """Create a new MySQL database."""
    command = f"MYSQL_PWD={mysql_password} mysql -u{mysql_username} -e 'CREATE DATABASE {db_name};'"
    stdin, stdout, stderr = ssh_client.exec_command(command)
    return stdout.read().decode(), stderr.read().decode()

def import_sql_file(ssh_client, mysql_username, mysql_password, db_name, sql_file):
    """Import an SQL file into the specified database."""
    # Save the SQL file temporarily
    temp_file_path = f"/tmp/{sql_file.filename}"
    sql_file.save(temp_file_path)

    try:
        command = f"MYSQL_PWD={mysql_password} mysql -u{mysql_username} {db_name} < {temp_file_path}"
        stdin, stdout, stderr = ssh_client.exec_command(command)
        
        # Wait for the command to complete
        stdout.channel.recv_exit_status()
        
        return stdout.read().decode(), stderr.read().decode()
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)  # Clean up the temp file
