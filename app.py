import os
import psutil
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from server_metrics import connect_ssh, get_metrics, control_service, get_databases, create_database, import_sql_file

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/monitor', methods=['POST'])
def monitor():
    hostname = request.form['hostname']
    username = request.form['username']
    password = request.form['password']

    ssh_client = connect_ssh(hostname, username, password)
    if ssh_client:
        session['hostname'] = hostname
        session['username'] = username
        session['password'] = password
        # Set a flag to show the welcome message
        return render_template('dashboard.html', show_welcome=True, service_status=False)
    else:
        return render_template('dashboard.html', error="Failed to connect to server.")

def get_cpu_usage():
    return psutil.cpu_percent(interval=1)

@app.route('/server_metrics')
def server_metrics():
    cpu_usage = get_cpu_usage()
    return jsonify({'cpu': {'usage': cpu_usage}})



@app.route('/service_status', methods=['POST'])
def service_status():
    ssh_client = connect_ssh(session['hostname'], session['username'], session['password'])
    if ssh_client:
        metrics = get_metrics(ssh_client)
        return render_template('dashboard.html', metrics=metrics, service_status=True)
    else:
        return render_template('dashboard.html', error="Failed to connect to server.")

@app.route('/service_control', methods=['POST'])
def service_control():
    service_name = request.form['service_name']
    action = request.form['action']

    ssh_client = connect_ssh(session['hostname'], session['username'], session['password'])
    if ssh_client:
        stdout, stderr = control_service(ssh_client, service_name, action)
        metrics = get_metrics(ssh_client)

        if stderr:
            return render_template('dashboard.html', error=stderr, metrics=metrics, service_status=True)
        
        return render_template('dashboard.html', message=f"{service_name} {action}ed successfully.", metrics=metrics, service_status=True)

    return render_template('dashboard.html', error="Failed to connect to server.")

@app.route('/disconnect', methods=['POST'])
def disconnect():
    session.clear()  # Clear session data
    return redirect('/')  # Redirect to the login page

@app.route('/database', methods=['POST'])
def database():
    mysql_username = request.form.get('mysql_username')
    mysql_password = request.form.get('mysql_password')

    ssh_client = connect_ssh(session['hostname'], session['username'], session['password'])
    if ssh_client and mysql_username and mysql_password:
        databases = get_databases(ssh_client, mysql_username, mysql_password)
        session['mysql_username'] = mysql_username
        session['mysql_password'] = mysql_password
        return render_template('database.html', databases=databases, success=True)
    else:
        return render_template('dashboard.html', error="Failed to connect to server or invalid credentials.")

@app.route('/create_database', methods=['POST'])
def create_database_route():
    db_name = request.form['db_name']
    mysql_username = session['mysql_username']
    mysql_password = session['mysql_password']

    ssh_client = connect_ssh(session['hostname'], session['username'], session['password'])
    if ssh_client:
        stdout, stderr = create_database(ssh_client, mysql_username, mysql_password, db_name)
        databases = get_databases(ssh_client, mysql_username, mysql_password)
        message = stdout if stdout else stderr
        return render_template('database.html', databases=databases, message=message)
    return render_template('dashboard.html', error="Failed to connect to server.")

@app.route('/import_sql', methods=['POST'])
def import_sql():
    if 'username' in session and 'hostname' in session:
        db_name = request.form['db_name']
        sql_file = request.files['sql_file']
        
        # Save the uploaded SQL file temporarily
        temp_file_path = f"/tmp/{sql_file.filename}"
        sql_file.save(temp_file_path)

        mysql_username = session['mysql_username']
        mysql_password = session['mysql_password']

        # Construct the command for importing the SQL file
        command = f"MYSQL_PWD={mysql_password} mysql -u{mysql_username} {db_name} < {temp_file_path}"

        ssh_client = connect_ssh(session['hostname'], session['username'], session['password'])
        if not ssh_client:
            return render_template('database.html', error="Could not connect to the server.")

        try:
            stdin, stdout, stderr = ssh_client.exec_command(command)

            # Wait for the command to complete
            stdout.channel.recv_exit_status()

            # Read output and error
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()

            # Clean up the temp file
            os.remove(temp_file_path)

            # Prepare the message for display
            message = output if output else error if error else "Import completed"

            databases = get_databases(ssh_client, mysql_username, mysql_password)
            return render_template('database.html', databases=databases, import_output=message)

        except Exception as e:
            return render_template('database.html', error=f"Error during import: {e}")

        finally:
            ssh_client.close()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
