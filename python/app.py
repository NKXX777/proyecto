from flask import Flask, render_template, request, url_for, flash, redirect, session    
from flask_mysqldb import MySQL
import MySQLdb.cursors
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import secrets, smtplib, qrcode, os, re
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import pymysql
pymysql.install_as_MySQLdb()

# ------------------ CONFIGURACIÓN FLASK Y MYSQL ------------------

app = Flask(__name__)
app.secret_key = 'colegiocarlosalban'

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'bdpython'
app.config['MYSQL_PORT'] = 3306  

mysql = MySQL(app)


# ------------------- FUNCIONES AUXILIARES -------------------

def generar_token(email):
    token = secrets.token_urlsafe(32)
    expiry = datetime.now() + timedelta(hours=1)
    cur = mysql.connection.cursor()
    cur.execute("UPDATE usuarios SET reset_token=%s, token_expiry=%s WHERE username=%s",
                (token, expiry, email))
    mysql.connection.commit()
    cur.close()
    return token


def enviar_correo_reset(email, token):
    enlace = url_for('reset', token=token, _external=True)
    cuerpo = f"""
Hola, solicitaste recuperar tu contraseña.
Haz click en el siguiente enlace:
{enlace}
Este enlace expira en 1 hora.
Si no lo solicitaste, ignora este mensaje.
"""
    remitente = 'pythoncontrasenas@gmail.com'
    clave = 'yqqp dtpo zmwv yuin'
    mensaje = MIMEText(cuerpo)
    mensaje['Subject'] = 'Recuperar contraseña'
    mensaje['From'] = remitente
    mensaje['To'] = email

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(remitente, clave)
    server.sendmail(remitente, email, mensaje.as_string())
    server.quit()


def enviar_qr_por_correo(email, nombre, qr_path):
    remitente = 'pythoncontrasenas@gmail.com'
    clave = 'yqqp dtpo zmwv yuin'
    asunto = 'Tu código QR de registro'
    cuerpo = f"""Hola {nombre},

Te has registrado correctamente en el sistema.
Adjunto encontrarás tu código QR personal para registrar asistencias.
Por favor, guárdalo o imprímelo para usarlo al ingresar o salir.

Saludos,
Equipo de control de asistencias.
"""

    mensaje = MIMEMultipart()
    mensaje['From'] = remitente
    mensaje['To'] = email
    mensaje['Subject'] = asunto
    mensaje.attach(MIMEText(cuerpo, 'plain'))

    if not os.path.exists(qr_path):
        raise FileNotFoundError(f"QR no encontrado: {qr_path}")

    with open(qr_path, 'rb') as adjunto:
        parte = MIMEBase('application', 'octet-stream')
        parte.set_payload(adjunto.read())
        encoders.encode_base64(parte)
        parte.add_header('Content-Disposition', f'attachment; filename={os.path.basename(qr_path)}')
        mensaje.attach(parte)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(remitente, clave)
    server.sendmail(remitente, email, mensaje.as_string())
    server.quit()


# ------------------- RUTAS -----------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_ingresada = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("""
        SELECT u.idUsuario, u.nombre, u.password, r.nombreRol
        FROM usuarios u
        JOIN usuario_rol ur ON u.idUsuario = ur.idUsuario
        JOIN roles r ON ur.idRol = r.idRol
        WHERE u.username = %s
        """, (username,))
        usuario = cur.fetchone()

        if usuario and check_password_hash(usuario[2], password_ingresada):
            session['usuario'] = usuario[1]
            session['idUsuario'] = usuario[0]
            session['rol'] = usuario[3]
            flash(f"¡Bienvenido {usuario[1]}!")

            cur.execute("""
            INSERT INTO registro_login(idUsuario, fecha)
            VALUES (%s, NOW())
            """, (usuario[0],))
            mysql.connection.commit()
            cur.close()

            if usuario[3] == 'admin':
                return redirect(url_for('dashboard'))
            elif usuario[3] == 'usuario':
                return redirect(url_for('movimientos'))
            else:
                flash('Rol de usuario no reconocido.')
                return redirect(url_for('login'))
        else:
            flash('Usuario o contraseña incorrecta.')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada correctamente.')
    return redirect(url_for('login'))


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form['apellido']
        username = request.form['username']
        password = request.form['password']

        if not re.match(r'[^@]+@[^@]+\.[^@]+', username):
            flash("Correo electrónico inválido.")
            return render_template('registro.html')

        cur = mysql.connection.cursor()
        try:
            cur.execute("SELECT idUsuario FROM usuarios WHERE username = %s", (username,))
            if cur.fetchone():
                flash("El correo ya está registrado.")
                return render_template('registro.html')

            hash_pw = generate_password_hash(password)
            cur.execute("""
                INSERT INTO usuarios(nombre, apellido, username, password)
                VALUES (%s, %s, %s, %s)
            """, (nombre, apellido, username, hash_pw))
            mysql.connection.commit()

            user_id = cur.lastrowid
            qr_folder = os.path.join(app.root_path, 'static', 'qr')
            os.makedirs(qr_folder, exist_ok=True)

            qr_data = f"usuario:{user_id}"
            img = qrcode.make(qr_data)
            qr_filename = f"qr_{user_id}.png"
            qr_path = os.path.join(qr_folder, qr_filename)
            img.save(qr_path)
            qr_web_path = f"/static/qr/{qr_filename}"

            cur.execute("UPDATE usuarios SET qr_path = %s WHERE idUsuario = %s",
                        (qr_web_path, user_id))
            mysql.connection.commit()

            cur.execute("INSERT INTO usuario_rol(idUsuario, idRol) VALUES (%s, %s)", (user_id, 2))
            mysql.connection.commit()

            try:
                enviar_qr_por_correo(username, nombre, qr_path)
                flash("Usuario registrado y QR enviado al correo.")
            except Exception as e:
                print(f"Error al enviar correo: {e}")
                flash("Usuario creado, pero hubo un problema al enviar el QR por correo.")

            return redirect(url_for('login'))
        except Exception as e:
            print(f"Error al registrar usuario: {e}")
            flash("Ocurrió un error al registrar el usuario.")
        finally:
            cur.close()
    return render_template('registro.html')

# ------------------- EJECUCIÓN -------------------

if __name__ == '__main__':
    app.run(port=5500, debug=True)
